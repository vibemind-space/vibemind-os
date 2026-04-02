"""Tests for PipelineStepAggregator."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_step_aggregator import PipelineStepAggregator


class TestCreateAggregation:
    def test_create_returns_id(self):
        a = PipelineStepAggregator()
        aid = a.create_aggregation("pipeline-1", ["step-a", "step-b"])
        assert aid.startswith("psag-")

    def test_create_with_strategy(self):
        a = PipelineStepAggregator()
        aid = a.create_aggregation("p1", ["s1"], strategy="merge")
        entry = a.get_aggregation(aid)
        assert entry["strategy"] == "merge"

    def test_create_empty_pipeline_id_returns_empty(self):
        a = PipelineStepAggregator()
        assert a.create_aggregation("", ["step-a"]) == ""

    def test_create_empty_steps_returns_empty(self):
        a = PipelineStepAggregator()
        assert a.create_aggregation("p1", []) == ""

    def test_create_invalid_strategy_returns_empty(self):
        a = PipelineStepAggregator()
        assert a.create_aggregation("p1", ["s1"], strategy="invalid") == ""

    def test_create_unique_ids(self):
        a = PipelineStepAggregator()
        ids = [a.create_aggregation("p1", ["s1"]) for _ in range(10)]
        assert len(set(ids)) == 10

    def test_create_default_strategy_is_collect(self):
        a = PipelineStepAggregator()
        aid = a.create_aggregation("p1", ["s1"])
        entry = a.get_aggregation(aid)
        assert entry["strategy"] == "collect"


class TestAddResult:
    def test_add_result_collect(self):
        a = PipelineStepAggregator()
        aid = a.create_aggregation("p1", ["s1"])
        assert a.add_result(aid, "s1", {"key": "value"}) is True
        entry = a.get_aggregation(aid)
        assert entry["results"]["s1"] == [{"key": "value"}]

    def test_add_multiple_results_collect(self):
        a = PipelineStepAggregator()
        aid = a.create_aggregation("p1", ["s1"])
        a.add_result(aid, "s1", "r1")
        a.add_result(aid, "s1", "r2")
        entry = a.get_aggregation(aid)
        assert entry["results"]["s1"] == ["r1", "r2"]

    def test_add_result_merge(self):
        a = PipelineStepAggregator()
        aid = a.create_aggregation("p1", ["s1"], strategy="merge")
        a.add_result(aid, "s1", {"a": 1})
        a.add_result(aid, "s1", {"b": 2})
        entry = a.get_aggregation(aid)
        assert entry["results"]["s1"] == {"a": 1, "b": 2}

    def test_add_result_sum(self):
        a = PipelineStepAggregator()
        aid = a.create_aggregation("p1", ["s1"], strategy="sum")
        a.add_result(aid, "s1", 10)
        a.add_result(aid, "s1", 5)
        entry = a.get_aggregation(aid)
        assert entry["results"]["s1"] == 15

    def test_add_result_nonexistent_aggregation(self):
        a = PipelineStepAggregator()
        assert a.add_result("psag-fake", "s1", "data") is False

    def test_add_result_empty_step_name(self):
        a = PipelineStepAggregator()
        aid = a.create_aggregation("p1", ["s1"])
        assert a.add_result(aid, "", "data") is False


class TestGetAggregation:
    def test_get_existing(self):
        a = PipelineStepAggregator()
        aid = a.create_aggregation("p1", ["s1", "s2"])
        result = a.get_aggregation(aid)
        assert result is not None
        assert result["pipeline_id"] == "p1"
        assert result["step_names"] == ["s1", "s2"]

    def test_get_nonexistent_returns_none(self):
        a = PipelineStepAggregator()
        assert a.get_aggregation("psag-doesnotexist") is None


class TestGetAggregations:
    def test_get_all(self):
        a = PipelineStepAggregator()
        a.create_aggregation("p1", ["s1"])
        a.create_aggregation("p2", ["s2"])
        results = a.get_aggregations()
        assert len(results) == 2

    def test_filter_by_pipeline_id(self):
        a = PipelineStepAggregator()
        a.create_aggregation("p1", ["s1"])
        a.create_aggregation("p2", ["s2"])
        a.create_aggregation("p1", ["s3"])
        results = a.get_aggregations(pipeline_id="p1")
        assert len(results) == 2
        assert all(r["pipeline_id"] == "p1" for r in results)

    def test_newest_first(self):
        a = PipelineStepAggregator()
        a.create_aggregation("p1", ["s1"])
        a.create_aggregation("p1", ["s2"])
        results = a.get_aggregations()
        assert results[0]["created_at"] >= results[1]["created_at"]

    def test_limit(self):
        a = PipelineStepAggregator()
        for i in range(10):
            a.create_aggregation("p1", [f"s{i}"])
        results = a.get_aggregations(limit=3)
        assert len(results) == 3

    def test_empty_results(self):
        a = PipelineStepAggregator()
        assert a.get_aggregations() == []


class TestGetAggregationCount:
    def test_total_count(self):
        a = PipelineStepAggregator()
        a.create_aggregation("p1", ["s1"])
        a.create_aggregation("p2", ["s2"])
        assert a.get_aggregation_count() == 2

    def test_count_by_pipeline_id(self):
        a = PipelineStepAggregator()
        a.create_aggregation("p1", ["s1"])
        a.create_aggregation("p2", ["s2"])
        a.create_aggregation("p1", ["s3"])
        assert a.get_aggregation_count(pipeline_id="p1") == 2
        assert a.get_aggregation_count(pipeline_id="p2") == 1

    def test_count_empty(self):
        a = PipelineStepAggregator()
        assert a.get_aggregation_count() == 0


class TestGetStats:
    def test_stats_structure(self):
        a = PipelineStepAggregator()
        stats = a.get_stats()
        assert "total_aggregations" in stats
        assert "total_results" in stats
        assert "unique_pipelines" in stats

    def test_stats_values(self):
        a = PipelineStepAggregator()
        aid1 = a.create_aggregation("p1", ["s1"])
        aid2 = a.create_aggregation("p2", ["s2"])
        a.add_result(aid1, "s1", "r1")
        a.add_result(aid1, "s1", "r2")
        a.add_result(aid2, "s2", "r3")
        stats = a.get_stats()
        assert stats["total_aggregations"] == 2
        assert stats["total_results"] == 3
        assert stats["unique_pipelines"] == 2

    def test_stats_empty(self):
        a = PipelineStepAggregator()
        stats = a.get_stats()
        assert stats["total_aggregations"] == 0
        assert stats["total_results"] == 0
        assert stats["unique_pipelines"] == 0


class TestReset:
    def test_reset_clears_entries(self):
        a = PipelineStepAggregator()
        a.create_aggregation("p1", ["s1"])
        a.reset()
        assert a.get_aggregation_count() == 0
        assert a.get_stats()["total_aggregations"] == 0

    def test_reset_clears_on_change(self):
        a = PipelineStepAggregator()
        a.on_change = lambda a, d: None
        a.reset()
        assert a.on_change is None


class TestCallbacks:
    def test_on_change_fires_on_create(self):
        a = PipelineStepAggregator()
        events = []
        a.on_change = lambda action, data: events.append((action, data))
        a.create_aggregation("p1", ["s1"])
        assert len(events) == 1
        assert events[0][0] == "aggregation_created"

    def test_on_change_fires_on_add_result(self):
        a = PipelineStepAggregator()
        aid = a.create_aggregation("p1", ["s1"])
        events = []
        a.on_change = lambda action, data: events.append((action, data))
        a.add_result(aid, "s1", "r1")
        assert len(events) == 1
        assert events[0][0] == "result_added"

    def test_callback_fires(self):
        a = PipelineStepAggregator()
        events = []
        a._callbacks["test"] = lambda action, data: events.append(action)
        a.create_aggregation("p1", ["s1"])
        assert "aggregation_created" in events

    def test_remove_callback(self):
        a = PipelineStepAggregator()
        a._callbacks["test"] = lambda a, d: None
        assert a.remove_callback("test") is True
        assert a.remove_callback("test") is False

    def test_callback_exception_silenced(self):
        a = PipelineStepAggregator()
        a._callbacks["bad"] = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
        aid = a.create_aggregation("p1", ["s1"])
        assert aid.startswith("psag-")

    def test_on_change_property(self):
        a = PipelineStepAggregator()
        assert a.on_change is None
        fn = lambda a, d: None
        a.on_change = fn
        assert a.on_change is fn


class TestPrune:
    def test_prune_evicts_oldest(self):
        a = PipelineStepAggregator()
        a.MAX_ENTRIES = 5
        for i in range(8):
            a.create_aggregation(f"p{i}", [f"s{i}"])
        assert len(a._state.entries) <= 6
