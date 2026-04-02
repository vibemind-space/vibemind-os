"""Tests for PipelineStepPrioritizer service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_step_prioritizer import PipelineStepPrioritizer


class TestSetPriority:
    """set_priority operations."""

    def test_set_priority_returns_string_id(self):
        p = PipelineStepPrioritizer()
        rid = p.set_priority("pipe-1", "step-a")
        assert isinstance(rid, str)
        assert rid.startswith("pspr-")

    def test_set_priority_ids_are_unique(self):
        p = PipelineStepPrioritizer()
        ids = [p.set_priority("pipe-1", f"step-{i}") for i in range(20)]
        assert len(set(ids)) == 20

    def test_set_priority_default_priority_zero(self):
        p = PipelineStepPrioritizer()
        rid = p.set_priority("pipe-1", "step-a")
        record = p.get_priority(rid)
        assert record["priority"] == 0

    def test_set_priority_custom_priority(self):
        p = PipelineStepPrioritizer()
        rid = p.set_priority("pipe-1", "step-a", priority=10)
        record = p.get_priority(rid)
        assert record["priority"] == 10

    def test_set_priority_with_metadata(self):
        p = PipelineStepPrioritizer()
        rid = p.set_priority("pipe-1", "step-a", metadata={"key": "val"})
        record = p.get_priority(rid)
        assert record["metadata"]["key"] == "val"

    def test_set_priority_metadata_default_empty_dict(self):
        p = PipelineStepPrioritizer()
        rid = p.set_priority("pipe-1", "step-a")
        record = p.get_priority(rid)
        assert record["metadata"] == {}

    def test_set_priority_metadata_is_copied(self):
        p = PipelineStepPrioritizer()
        meta = {"nested": {"x": 1}}
        rid = p.set_priority("pipe-1", "step-a", metadata=meta)
        meta["nested"]["x"] = 999
        record = p.get_priority(rid)
        assert record["metadata"]["nested"]["x"] == 1

    def test_set_priority_stores_pipeline_id(self):
        p = PipelineStepPrioritizer()
        rid = p.set_priority("my-pipeline", "step-a")
        record = p.get_priority(rid)
        assert record["pipeline_id"] == "my-pipeline"

    def test_set_priority_stores_step_name(self):
        p = PipelineStepPrioritizer()
        rid = p.set_priority("pipe-1", "my-step")
        record = p.get_priority(rid)
        assert record["step_name"] == "my-step"


class TestGetPriority:
    """get_priority method."""

    def test_get_priority_existing(self):
        p = PipelineStepPrioritizer()
        rid = p.set_priority("pipe-1", "step-a", priority=5)
        result = p.get_priority(rid)
        assert result is not None
        assert result["record_id"] == rid

    def test_get_priority_nonexistent(self):
        p = PipelineStepPrioritizer()
        assert p.get_priority("pspr-nonexistent") is None

    def test_get_priority_returns_dict_copy(self):
        p = PipelineStepPrioritizer()
        rid = p.set_priority("pipe-1", "step-a")
        r1 = p.get_priority(rid)
        r2 = p.get_priority(rid)
        assert r1 is not r2
        assert r1 == r2


class TestGetPriorities:
    """get_priorities listing."""

    def test_get_priorities_returns_list(self):
        p = PipelineStepPrioritizer()
        p.set_priority("pipe-1", "step-a")
        result = p.get_priorities()
        assert isinstance(result, list)
        assert len(result) == 1

    def test_get_priorities_newest_first(self):
        p = PipelineStepPrioritizer()
        id1 = p.set_priority("pipe-1", "step-a")
        id2 = p.set_priority("pipe-1", "step-b")
        results = p.get_priorities()
        assert results[0]["record_id"] == id2
        assert results[1]["record_id"] == id1

    def test_get_priorities_filter_by_pipeline_id(self):
        p = PipelineStepPrioritizer()
        p.set_priority("pipe-a", "step-1")
        p.set_priority("pipe-b", "step-2")
        p.set_priority("pipe-a", "step-3")
        results = p.get_priorities(pipeline_id="pipe-a")
        assert len(results) == 2
        assert all(r["pipeline_id"] == "pipe-a" for r in results)

    def test_get_priorities_respects_limit(self):
        p = PipelineStepPrioritizer()
        for i in range(10):
            p.set_priority("pipe-1", f"step-{i}")
        results = p.get_priorities(limit=3)
        assert len(results) == 3

    def test_get_priorities_empty(self):
        p = PipelineStepPrioritizer()
        assert p.get_priorities() == []

    def test_get_priorities_filter_returns_empty_for_unknown_pipeline(self):
        p = PipelineStepPrioritizer()
        p.set_priority("pipe-a", "step-1")
        results = p.get_priorities(pipeline_id="pipe-unknown")
        assert results == []

    def test_get_priorities_returns_dicts(self):
        p = PipelineStepPrioritizer()
        p.set_priority("pipe-1", "step-a")
        p.set_priority("pipe-1", "step-b")
        results = p.get_priorities()
        assert all(isinstance(r, dict) for r in results)


class TestGetPriorityCount:
    """get_priority_count method."""

    def test_count_all(self):
        p = PipelineStepPrioritizer()
        for i in range(5):
            p.set_priority("pipe-1", f"step-{i}")
        assert p.get_priority_count() == 5

    def test_count_by_pipeline_id(self):
        p = PipelineStepPrioritizer()
        p.set_priority("pipe-a", "step-1")
        p.set_priority("pipe-b", "step-2")
        p.set_priority("pipe-a", "step-3")
        assert p.get_priority_count(pipeline_id="pipe-a") == 2
        assert p.get_priority_count(pipeline_id="pipe-b") == 1
        assert p.get_priority_count(pipeline_id="pipe-c") == 0

    def test_count_empty(self):
        p = PipelineStepPrioritizer()
        assert p.get_priority_count() == 0


class TestGetStats:
    """get_stats method."""

    def test_stats_empty(self):
        p = PipelineStepPrioritizer()
        stats = p.get_stats()
        assert stats["total_records"] == 0
        assert stats["unique_pipelines"] == 0
        assert stats["unique_steps"] == 0
        assert stats["callbacks"] == 0

    def test_stats_populated(self):
        p = PipelineStepPrioritizer()
        p.set_priority("pipe-a", "step-1")
        p.set_priority("pipe-b", "step-2")
        p.set_priority("pipe-a", "step-3")
        stats = p.get_stats()
        assert stats["total_records"] == 3
        assert stats["unique_pipelines"] == 2
        assert stats["unique_steps"] == 3

    def test_stats_returns_dict(self):
        p = PipelineStepPrioritizer()
        assert isinstance(p.get_stats(), dict)


class TestReset:
    """reset method."""

    def test_reset_clears_entries(self):
        p = PipelineStepPrioritizer()
        p.set_priority("pipe-1", "step-a")
        p.set_priority("pipe-1", "step-b")
        assert p.get_priority_count() == 2
        p.reset()
        assert p.get_priority_count() == 0

    def test_reset_clears_callbacks(self):
        p = PipelineStepPrioritizer()
        p._callbacks["mycb"] = lambda a, d: None
        p.reset()
        assert len(p._callbacks) == 0

    def test_reset_clears_on_change(self):
        p = PipelineStepPrioritizer()
        p.on_change = lambda a, d: None
        p.reset()
        assert p.on_change is None


class TestCallbacks:
    """Callback and event system."""

    def test_on_change_fires_on_set_priority(self):
        p = PipelineStepPrioritizer()
        events = []
        p.on_change = lambda action, data: events.append((action, data))
        p.set_priority("pipe-1", "step-a")
        assert len(events) == 1
        assert events[0][0] == "set_priority"

    def test_on_change_property_getter(self):
        p = PipelineStepPrioritizer()
        assert p.on_change is None
        cb = lambda a, d: None
        p.on_change = cb
        assert p.on_change is cb

    def test_on_change_exception_is_silent(self):
        p = PipelineStepPrioritizer()
        p.on_change = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
        rid = p.set_priority("pipe-1", "step-a")
        assert rid.startswith("pspr-")

    def test_remove_callback_returns_true_if_found(self):
        p = PipelineStepPrioritizer()
        p._callbacks["mycb"] = lambda a, d: None
        assert p.remove_callback("mycb") is True

    def test_remove_callback_returns_false_if_not_found(self):
        p = PipelineStepPrioritizer()
        assert p.remove_callback("nonexistent") is False

    def test_named_callback_fires(self):
        p = PipelineStepPrioritizer()
        fired = []
        p._callbacks["tracker"] = lambda a, d: fired.append(a)
        p.set_priority("pipe-1", "step-a")
        assert "set_priority" in fired

    def test_named_callback_exception_silent(self):
        p = PipelineStepPrioritizer()
        p._callbacks["bad"] = lambda a, d: 1 / 0
        rid = p.set_priority("pipe-1", "step-a")
        assert rid.startswith("pspr-")

    def test_on_change_fires_before_named_callbacks(self):
        p = PipelineStepPrioritizer()
        order = []
        p.on_change = lambda a, d: order.append("on_change")
        p._callbacks["named"] = lambda a, d: order.append("named")
        p.set_priority("pipe-1", "step-a")
        assert order == ["on_change", "named"]


class TestPruning:
    """Eviction when exceeding MAX_ENTRIES."""

    def test_prune_removes_oldest_quarter(self):
        p = PipelineStepPrioritizer()
        p.MAX_ENTRIES = 8
        ids = []
        for i in range(10):
            ids.append(p.set_priority("pipe-1", f"step-{i}"))
        # After exceeding 8, oldest quarter (2) should be removed
        # 10 entries triggers prune: removes 10//4 = 2 oldest
        remaining = p.get_priority_count()
        assert remaining == 8
        # oldest two should be gone
        assert p.get_priority(ids[0]) is None
        assert p.get_priority(ids[1]) is None
        # newest should still exist
        assert p.get_priority(ids[9]) is not None

    def test_prune_preserves_newest(self):
        p = PipelineStepPrioritizer()
        p.MAX_ENTRIES = 4
        ids = []
        for i in range(6):
            ids.append(p.set_priority("pipe-1", f"step-{i}"))
        # last entry should always survive
        assert p.get_priority(ids[-1]) is not None


class TestUniqueIds:
    """ID uniqueness guarantees."""

    def test_ids_unique_across_many(self):
        p = PipelineStepPrioritizer()
        ids = set()
        for i in range(100):
            rid = p.set_priority("pipe-1", f"step-{i}")
            ids.add(rid)
        assert len(ids) == 100

    def test_ids_have_correct_prefix(self):
        p = PipelineStepPrioritizer()
        for i in range(5):
            rid = p.set_priority("pipe-1", f"step-{i}")
            assert rid.startswith("pspr-")
