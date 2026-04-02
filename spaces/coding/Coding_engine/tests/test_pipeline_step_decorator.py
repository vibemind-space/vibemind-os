"""Tests for the PipelineStepDecorator service."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_step_decorator import PipelineStepDecorator


class TestDecorate:
    def test_decorate_returns_id(self):
        svc = PipelineStepDecorator()
        dec_id = svc.decorate("pipe-1", "step-a")
        assert dec_id.startswith("psdc-")

    def test_decorate_with_tags(self):
        svc = PipelineStepDecorator()
        dec_id = svc.decorate("pipe-1", "step-a", tags=["fast", "gpu"])
        entry = svc.get_decoration(dec_id)
        assert entry["tags"] == ["fast", "gpu"]

    def test_decorate_with_metadata(self):
        svc = PipelineStepDecorator()
        dec_id = svc.decorate("pipe-1", "step-a", metadata={"priority": 5})
        entry = svc.get_decoration(dec_id)
        assert entry["metadata"]["priority"] == 5

    def test_decorate_no_tags_no_metadata(self):
        svc = PipelineStepDecorator()
        dec_id = svc.decorate("pipe-1", "step-a")
        entry = svc.get_decoration(dec_id)
        assert entry["tags"] == []
        assert entry["metadata"] == {}

    def test_decorate_unique_ids(self):
        svc = PipelineStepDecorator()
        ids = {svc.decorate("pipe-1", "step-a") for _ in range(20)}
        assert len(ids) == 20


class TestGetDecoration:
    def test_get_existing(self):
        svc = PipelineStepDecorator()
        dec_id = svc.decorate("pipe-1", "step-a", tags=["x"])
        result = svc.get_decoration(dec_id)
        assert result is not None
        assert result["pipeline_id"] == "pipe-1"
        assert result["step_name"] == "step-a"

    def test_get_nonexistent(self):
        svc = PipelineStepDecorator()
        assert svc.get_decoration("psdc-doesnotexist") is None

    def test_get_returns_copy(self):
        svc = PipelineStepDecorator()
        dec_id = svc.decorate("pipe-1", "step-a")
        r1 = svc.get_decoration(dec_id)
        r2 = svc.get_decoration(dec_id)
        assert r1 is not r2


class TestGetDecorations:
    def test_filter_by_pipeline(self):
        svc = PipelineStepDecorator()
        svc.decorate("pipe-1", "step-a")
        svc.decorate("pipe-2", "step-b")
        svc.decorate("pipe-1", "step-c")
        results = svc.get_decorations(pipeline_id="pipe-1")
        assert len(results) == 2
        assert all(r["pipeline_id"] == "pipe-1" for r in results)

    def test_filter_by_step(self):
        svc = PipelineStepDecorator()
        svc.decorate("pipe-1", "step-a")
        svc.decorate("pipe-2", "step-a")
        svc.decorate("pipe-1", "step-b")
        results = svc.get_decorations(step_name="step-a")
        assert len(results) == 2

    def test_newest_first(self):
        svc = PipelineStepDecorator()
        id1 = svc.decorate("pipe-1", "step-a")
        id2 = svc.decorate("pipe-1", "step-b")
        results = svc.get_decorations()
        assert results[0]["id"] == id2
        assert results[1]["id"] == id1

    def test_limit(self):
        svc = PipelineStepDecorator()
        for i in range(10):
            svc.decorate("pipe-1", f"step-{i}")
        results = svc.get_decorations(limit=3)
        assert len(results) == 3

    def test_no_filters_returns_all(self):
        svc = PipelineStepDecorator()
        for i in range(5):
            svc.decorate(f"pipe-{i}", "step-a")
        results = svc.get_decorations()
        assert len(results) == 5


class TestAddTag:
    def test_add_tag_success(self):
        svc = PipelineStepDecorator()
        dec_id = svc.decorate("pipe-1", "step-a")
        assert svc.add_tag(dec_id, "new-tag") is True
        entry = svc.get_decoration(dec_id)
        assert "new-tag" in entry["tags"]

    def test_add_tag_nonexistent(self):
        svc = PipelineStepDecorator()
        assert svc.add_tag("psdc-nope", "tag") is False

    def test_add_duplicate_tag(self):
        svc = PipelineStepDecorator()
        dec_id = svc.decorate("pipe-1", "step-a", tags=["x"])
        svc.add_tag(dec_id, "x")
        entry = svc.get_decoration(dec_id)
        assert entry["tags"].count("x") == 1


class TestGetDecorationCount:
    def test_total_count(self):
        svc = PipelineStepDecorator()
        svc.decorate("pipe-1", "step-a")
        svc.decorate("pipe-2", "step-b")
        assert svc.get_decoration_count() == 2

    def test_count_by_pipeline(self):
        svc = PipelineStepDecorator()
        svc.decorate("pipe-1", "step-a")
        svc.decorate("pipe-1", "step-b")
        svc.decorate("pipe-2", "step-c")
        assert svc.get_decoration_count(pipeline_id="pipe-1") == 2
        assert svc.get_decoration_count(pipeline_id="pipe-2") == 1

    def test_count_empty(self):
        svc = PipelineStepDecorator()
        assert svc.get_decoration_count() == 0


class TestGetStats:
    def test_stats_empty(self):
        svc = PipelineStepDecorator()
        stats = svc.get_stats()
        assert stats["total_decorations"] == 0
        assert stats["unique_tags"] == 0
        assert stats["unique_pipelines"] == 0

    def test_stats_populated(self):
        svc = PipelineStepDecorator()
        svc.decorate("pipe-1", "step-a", tags=["fast", "gpu"])
        svc.decorate("pipe-2", "step-b", tags=["fast", "cpu"])
        stats = svc.get_stats()
        assert stats["total_decorations"] == 2
        assert stats["unique_tags"] == 3  # fast, gpu, cpu
        assert stats["unique_pipelines"] == 2


class TestReset:
    def test_reset_clears_entries(self):
        svc = PipelineStepDecorator()
        svc.decorate("pipe-1", "step-a")
        svc.reset()
        assert svc.get_decoration_count() == 0

    def test_reset_clears_callbacks(self):
        svc = PipelineStepDecorator()
        svc._callbacks["test"] = lambda a, d: None
        svc.reset()
        assert len(svc._callbacks) == 0

    def test_reset_clears_on_change(self):
        svc = PipelineStepDecorator()
        svc.on_change = lambda a, d: None
        svc.reset()
        assert svc.on_change is None


class TestCallbacks:
    def test_fire_on_decorate(self):
        svc = PipelineStepDecorator()
        events = []
        svc._callbacks["log"] = lambda action, data: events.append((action, data))
        svc.decorate("pipe-1", "step-a")
        assert len(events) == 1
        assert events[0][0] == "decoration_created"

    def test_fire_on_add_tag(self):
        svc = PipelineStepDecorator()
        events = []
        svc._callbacks["log"] = lambda action, data: events.append((action, data))
        dec_id = svc.decorate("pipe-1", "step-a")
        svc.add_tag(dec_id, "tag-1")
        assert any(e[0] == "tag_added" for e in events)

    def test_on_change_property(self):
        svc = PipelineStepDecorator()
        events = []
        svc.on_change = lambda action, data: events.append(action)
        svc.decorate("pipe-1", "step-a")
        assert "decoration_created" in events

    def test_remove_callback(self):
        svc = PipelineStepDecorator()
        svc._callbacks["test"] = lambda a, d: None
        assert svc.remove_callback("test") is True
        assert svc.remove_callback("test") is False

    def test_fire_silent_exception(self):
        svc = PipelineStepDecorator()
        svc._callbacks["bad"] = lambda a, d: (_ for _ in ()).throw(RuntimeError("boom"))
        # Should not raise
        svc.decorate("pipe-1", "step-a")


class TestPrune:
    def test_prune_excess_entries(self):
        svc = PipelineStepDecorator()
        original_max = PipelineStepDecorator.MAX_ENTRIES
        PipelineStepDecorator.MAX_ENTRIES = 5
        try:
            for i in range(8):
                svc.decorate("pipe-1", f"step-{i}")
            assert len(svc._state.entries) <= 6
        finally:
            PipelineStepDecorator.MAX_ENTRIES = original_max
