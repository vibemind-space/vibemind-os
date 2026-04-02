"""Tests for PipelineStepIsolator service."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_step_isolator import PipelineStepIsolator


class TestCreateIsolation:
    def test_create_isolation_returns_id(self):
        iso = PipelineStepIsolator()
        result = iso.create_isolation("pipe-1", "step-a")
        assert result.startswith("psis-")
        assert len(result) > 5

    def test_create_isolation_with_context(self):
        iso = PipelineStepIsolator()
        ctx = {"key": "value", "nested": {"a": 1}}
        iid = iso.create_isolation("pipe-1", "step-a", context=ctx)
        entry = iso.get_isolation(iid)
        assert entry["context"]["key"] == "value"
        assert entry["context"]["nested"]["a"] == 1

    def test_create_isolation_deep_copies_context(self):
        iso = PipelineStepIsolator()
        ctx = {"data": [1, 2, 3]}
        iid = iso.create_isolation("pipe-1", "step-a", context=ctx)
        ctx["data"].append(4)
        entry = iso.get_isolation(iid)
        assert entry["context"]["data"] == [1, 2, 3]

    def test_create_isolation_empty_pipeline_id(self):
        iso = PipelineStepIsolator()
        result = iso.create_isolation("", "step-a")
        assert result == ""

    def test_create_isolation_empty_step_name(self):
        iso = PipelineStepIsolator()
        result = iso.create_isolation("pipe-1", "")
        assert result == ""

    def test_create_isolation_unique_ids(self):
        iso = PipelineStepIsolator()
        ids = set()
        for i in range(20):
            iid = iso.create_isolation("pipe-1", f"step-{i}")
            ids.add(iid)
        assert len(ids) == 20


class TestGetIsolation:
    def test_get_isolation_found(self):
        iso = PipelineStepIsolator()
        iid = iso.create_isolation("pipe-1", "step-a")
        entry = iso.get_isolation(iid)
        assert entry is not None
        assert entry["pipeline_id"] == "pipe-1"
        assert entry["step_name"] == "step-a"
        assert entry["isolation_id"] == iid

    def test_get_isolation_not_found(self):
        iso = PipelineStepIsolator()
        assert iso.get_isolation("nonexistent") is None

    def test_get_isolation_has_timestamps(self):
        iso = PipelineStepIsolator()
        iid = iso.create_isolation("pipe-1", "step-a")
        entry = iso.get_isolation(iid)
        assert "created_at" in entry
        assert "updated_at" in entry
        assert entry["created_at"] > 0


class TestGetContext:
    def test_get_context_returns_deep_copy(self):
        iso = PipelineStepIsolator()
        iid = iso.create_isolation("pipe-1", "step-a", context={"x": [1, 2]})
        ctx1 = iso.get_context(iid)
        ctx1["x"].append(3)
        ctx2 = iso.get_context(iid)
        assert ctx2["x"] == [1, 2]

    def test_get_context_not_found(self):
        iso = PipelineStepIsolator()
        assert iso.get_context("nonexistent") is None

    def test_get_context_empty_default(self):
        iso = PipelineStepIsolator()
        iid = iso.create_isolation("pipe-1", "step-a")
        ctx = iso.get_context(iid)
        assert ctx == {}


class TestUpdateContext:
    def test_update_context_merges(self):
        iso = PipelineStepIsolator()
        iid = iso.create_isolation("pipe-1", "step-a", context={"a": 1})
        result = iso.update_context(iid, {"b": 2})
        assert result is True
        ctx = iso.get_context(iid)
        assert ctx == {"a": 1, "b": 2}

    def test_update_context_overwrites_existing_key(self):
        iso = PipelineStepIsolator()
        iid = iso.create_isolation("pipe-1", "step-a", context={"a": 1})
        iso.update_context(iid, {"a": 99})
        ctx = iso.get_context(iid)
        assert ctx["a"] == 99

    def test_update_context_not_found(self):
        iso = PipelineStepIsolator()
        assert iso.update_context("nonexistent", {"a": 1}) is False

    def test_update_context_deep_copies_updates(self):
        iso = PipelineStepIsolator()
        iid = iso.create_isolation("pipe-1", "step-a")
        updates = {"data": [1, 2]}
        iso.update_context(iid, updates)
        updates["data"].append(3)
        ctx = iso.get_context(iid)
        assert ctx["data"] == [1, 2]

    def test_update_context_updates_timestamp(self):
        iso = PipelineStepIsolator()
        iid = iso.create_isolation("pipe-1", "step-a")
        entry_before = iso.get_isolation(iid)
        time.sleep(0.01)
        iso.update_context(iid, {"x": 1})
        entry_after = iso.get_isolation(iid)
        assert entry_after["updated_at"] >= entry_before["updated_at"]


class TestGetIsolations:
    def test_get_isolations_all(self):
        iso = PipelineStepIsolator()
        iso.create_isolation("pipe-1", "step-a")
        iso.create_isolation("pipe-2", "step-b")
        results = iso.get_isolations()
        assert len(results) == 2

    def test_get_isolations_filter_by_pipeline(self):
        iso = PipelineStepIsolator()
        iso.create_isolation("pipe-1", "step-a")
        iso.create_isolation("pipe-2", "step-b")
        iso.create_isolation("pipe-1", "step-c")
        results = iso.get_isolations(pipeline_id="pipe-1")
        assert len(results) == 2
        assert all(r["pipeline_id"] == "pipe-1" for r in results)

    def test_get_isolations_newest_first(self):
        iso = PipelineStepIsolator()
        iso.create_isolation("pipe-1", "step-a")
        iso.create_isolation("pipe-1", "step-b")
        results = iso.get_isolations()
        assert results[0]["created_at"] >= results[1]["created_at"]

    def test_get_isolations_respects_limit(self):
        iso = PipelineStepIsolator()
        for i in range(10):
            iso.create_isolation("pipe-1", f"step-{i}")
        results = iso.get_isolations(limit=3)
        assert len(results) == 3


class TestGetIsolationCount:
    def test_count_all(self):
        iso = PipelineStepIsolator()
        iso.create_isolation("pipe-1", "step-a")
        iso.create_isolation("pipe-2", "step-b")
        assert iso.get_isolation_count() == 2

    def test_count_filtered(self):
        iso = PipelineStepIsolator()
        iso.create_isolation("pipe-1", "step-a")
        iso.create_isolation("pipe-2", "step-b")
        iso.create_isolation("pipe-1", "step-c")
        assert iso.get_isolation_count("pipe-1") == 2
        assert iso.get_isolation_count("pipe-2") == 1

    def test_count_empty(self):
        iso = PipelineStepIsolator()
        assert iso.get_isolation_count() == 0


class TestGetStats:
    def test_stats_empty(self):
        iso = PipelineStepIsolator()
        stats = iso.get_stats()
        assert stats["total_isolations"] == 0
        assert stats["unique_pipelines"] == 0
        assert stats["unique_steps"] == 0

    def test_stats_populated(self):
        iso = PipelineStepIsolator()
        iso.create_isolation("pipe-1", "step-a")
        iso.create_isolation("pipe-1", "step-b")
        iso.create_isolation("pipe-2", "step-a")
        stats = iso.get_stats()
        assert stats["total_isolations"] == 3
        assert stats["unique_pipelines"] == 2
        assert stats["unique_steps"] == 2


class TestReset:
    def test_reset_clears_entries(self):
        iso = PipelineStepIsolator()
        iso.create_isolation("pipe-1", "step-a")
        iso.reset()
        assert iso.get_isolation_count() == 0

    def test_reset_clears_callbacks(self):
        iso = PipelineStepIsolator()
        iso._callbacks["test"] = lambda a, d: None
        iso.on_change = lambda a, d: None
        iso.reset()
        assert iso._callbacks == {}
        assert iso.on_change is None


class TestCallbacksAndEvents:
    def test_on_change_fires_on_create(self):
        iso = PipelineStepIsolator()
        events = []
        iso.on_change = lambda action, data: events.append((action, data))
        iso.create_isolation("pipe-1", "step-a")
        assert len(events) == 1
        assert events[0][0] == "isolation_created"

    def test_on_change_fires_on_update(self):
        iso = PipelineStepIsolator()
        events = []
        iid = iso.create_isolation("pipe-1", "step-a")
        iso.on_change = lambda action, data: events.append((action, data))
        iso.update_context(iid, {"x": 1})
        assert len(events) == 1
        assert events[0][0] == "context_updated"

    def test_callback_exception_is_silent(self):
        iso = PipelineStepIsolator()
        iso.on_change = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
        iid = iso.create_isolation("pipe-1", "step-a")
        assert iid != ""

    def test_remove_callback(self):
        iso = PipelineStepIsolator()
        iso._callbacks["cb1"] = lambda a, d: None
        assert iso.remove_callback("cb1") is True
        assert iso.remove_callback("cb1") is False

    def test_named_callbacks_fire(self):
        iso = PipelineStepIsolator()
        events = []
        iso._callbacks["my_cb"] = lambda a, d: events.append(a)
        iso.create_isolation("pipe-1", "step-a")
        assert "isolation_created" in events


class TestPruning:
    def test_prune_removes_oldest(self):
        iso = PipelineStepIsolator()
        iso.MAX_ENTRIES = 5
        for i in range(8):
            iso.create_isolation("pipe-1", f"step-{i}")
        assert iso.get_isolation_count() <= 6


class TestCrossContamination:
    def test_isolation_contexts_are_independent(self):
        iso = PipelineStepIsolator()
        id1 = iso.create_isolation("pipe-1", "step-a", context={"shared": [1]})
        id2 = iso.create_isolation("pipe-1", "step-b", context={"shared": [1]})
        iso.update_context(id1, {"shared": [1, 2, 3]})
        ctx2 = iso.get_context(id2)
        assert ctx2["shared"] == [1]
