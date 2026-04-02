"""Tests for PipelineStepCorrelator."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_step_correlator import PipelineStepCorrelator


class TestCorrelate:
    def test_correlate_returns_id(self):
        c = PipelineStepCorrelator()
        cid = c.correlate("pipeline-1", ["step-a", "step-b"])
        assert cid.startswith("psco-")

    def test_correlate_with_key_and_metadata(self):
        c = PipelineStepCorrelator()
        cid = c.correlate("p1", ["s1"], correlation_key="key-1", metadata={"env": "prod"})
        entry = c.get_correlation(cid)
        assert entry["correlation_key"] == "key-1"
        assert entry["metadata"]["env"] == "prod"

    def test_correlate_empty_pipeline_id_returns_empty(self):
        c = PipelineStepCorrelator()
        assert c.correlate("", ["step-a"]) == ""

    def test_correlate_empty_steps_returns_empty(self):
        c = PipelineStepCorrelator()
        assert c.correlate("p1", []) == ""

    def test_correlate_unique_ids(self):
        c = PipelineStepCorrelator()
        ids = [c.correlate("p1", ["s1"]) for _ in range(10)]
        assert len(set(ids)) == 10


class TestGetCorrelation:
    def test_get_existing(self):
        c = PipelineStepCorrelator()
        cid = c.correlate("p1", ["s1", "s2"])
        result = c.get_correlation(cid)
        assert result is not None
        assert result["pipeline_id"] == "p1"
        assert result["step_names"] == ["s1", "s2"]

    def test_get_nonexistent_returns_none(self):
        c = PipelineStepCorrelator()
        assert c.get_correlation("psco-doesnotexist") is None


class TestGetCorrelations:
    def test_get_all(self):
        c = PipelineStepCorrelator()
        c.correlate("p1", ["s1"])
        c.correlate("p2", ["s2"])
        results = c.get_correlations()
        assert len(results) == 2

    def test_filter_by_pipeline_id(self):
        c = PipelineStepCorrelator()
        c.correlate("p1", ["s1"])
        c.correlate("p2", ["s2"])
        c.correlate("p1", ["s3"])
        results = c.get_correlations(pipeline_id="p1")
        assert len(results) == 2
        assert all(r["pipeline_id"] == "p1" for r in results)

    def test_newest_first(self):
        c = PipelineStepCorrelator()
        c.correlate("p1", ["s1"])
        c.correlate("p1", ["s2"])
        results = c.get_correlations()
        assert results[0]["created_at"] >= results[1]["created_at"]

    def test_limit(self):
        c = PipelineStepCorrelator()
        for i in range(10):
            c.correlate("p1", [f"s{i}"])
        results = c.get_correlations(limit=3)
        assert len(results) == 3

    def test_empty_results(self):
        c = PipelineStepCorrelator()
        assert c.get_correlations() == []


class TestAddStepToCorrelation:
    def test_add_step(self):
        c = PipelineStepCorrelator()
        cid = c.correlate("p1", ["s1"])
        assert c.add_step_to_correlation(cid, "s2") is True
        entry = c.get_correlation(cid)
        assert "s2" in entry["step_names"]

    def test_add_duplicate_step_returns_false(self):
        c = PipelineStepCorrelator()
        cid = c.correlate("p1", ["s1"])
        assert c.add_step_to_correlation(cid, "s1") is False

    def test_add_step_nonexistent_correlation(self):
        c = PipelineStepCorrelator()
        assert c.add_step_to_correlation("psco-fake", "s1") is False

    def test_add_empty_step_returns_false(self):
        c = PipelineStepCorrelator()
        cid = c.correlate("p1", ["s1"])
        assert c.add_step_to_correlation(cid, "") is False


class TestGetCorrelationCount:
    def test_total_count(self):
        c = PipelineStepCorrelator()
        c.correlate("p1", ["s1"])
        c.correlate("p2", ["s2"])
        assert c.get_correlation_count() == 2

    def test_count_by_pipeline_id(self):
        c = PipelineStepCorrelator()
        c.correlate("p1", ["s1"])
        c.correlate("p2", ["s2"])
        c.correlate("p1", ["s3"])
        assert c.get_correlation_count(pipeline_id="p1") == 2
        assert c.get_correlation_count(pipeline_id="p2") == 1

    def test_count_empty(self):
        c = PipelineStepCorrelator()
        assert c.get_correlation_count() == 0


class TestGetStats:
    def test_stats_structure(self):
        c = PipelineStepCorrelator()
        stats = c.get_stats()
        assert "total_correlations" in stats
        assert "total_steps_correlated" in stats
        assert "unique_pipelines" in stats

    def test_stats_values(self):
        c = PipelineStepCorrelator()
        c.correlate("p1", ["s1", "s2"])
        c.correlate("p2", ["s3"])
        stats = c.get_stats()
        assert stats["total_correlations"] == 2
        assert stats["total_steps_correlated"] == 3
        assert stats["unique_pipelines"] == 2

    def test_stats_empty(self):
        c = PipelineStepCorrelator()
        stats = c.get_stats()
        assert stats["total_correlations"] == 0
        assert stats["total_steps_correlated"] == 0
        assert stats["unique_pipelines"] == 0


class TestReset:
    def test_reset_clears_entries(self):
        c = PipelineStepCorrelator()
        c.correlate("p1", ["s1"])
        c.reset()
        assert c.get_correlation_count() == 0
        assert c.get_stats()["total_correlations"] == 0

    def test_reset_clears_on_change(self):
        c = PipelineStepCorrelator()
        c.on_change = lambda a, d: None
        c.reset()
        assert c.on_change is None


class TestCallbacks:
    def test_on_change_fires_on_correlate(self):
        c = PipelineStepCorrelator()
        events = []
        c.on_change = lambda action, data: events.append((action, data))
        c.correlate("p1", ["s1"])
        assert len(events) == 1
        assert events[0][0] == "correlation_created"

    def test_callback_fires(self):
        c = PipelineStepCorrelator()
        events = []
        c._callbacks["test"] = lambda action, data: events.append(action)
        c.correlate("p1", ["s1"])
        assert "correlation_created" in events

    def test_remove_callback(self):
        c = PipelineStepCorrelator()
        c._callbacks["test"] = lambda a, d: None
        assert c.remove_callback("test") is True
        assert c.remove_callback("test") is False

    def test_callback_exception_silenced(self):
        c = PipelineStepCorrelator()
        c._callbacks["bad"] = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
        # Should not raise
        cid = c.correlate("p1", ["s1"])
        assert cid.startswith("psco-")

    def test_on_change_property(self):
        c = PipelineStepCorrelator()
        assert c.on_change is None
        fn = lambda a, d: None
        c.on_change = fn
        assert c.on_change is fn


class TestPrune:
    def test_prune_evicts_oldest(self):
        c = PipelineStepCorrelator()
        c.MAX_ENTRIES = 5
        for i in range(8):
            c.correlate(f"p{i}", [f"s{i}"])
        assert len(c._state.entries) <= 6
