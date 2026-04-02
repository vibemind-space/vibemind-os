"""Tests for PipelineDataPatcher service."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.services.pipeline_data_patcher import PipelineDataPatcher


class TestApplyPatchBasic:
    """Basic patch application."""

    def test_apply_patch_returns_string_id(self):
        patcher = PipelineDataPatcher()
        patch_id = patcher.apply_patch({"key": "value"}, {"key": "new"})
        assert isinstance(patch_id, str)
        assert patch_id.startswith("pdpa-")

    def test_apply_patch_ids_are_unique(self):
        patcher = PipelineDataPatcher()
        ids = [patcher.apply_patch({"i": i}, {"i": i + 100}) for i in range(10)]
        assert len(set(ids)) == 10

    def test_apply_patch_deep_copies_data(self):
        patcher = PipelineDataPatcher()
        original = {"nested": {"a": 1}}
        patch_id = patcher.apply_patch(original, {"nested": {"a": 99}})
        original["nested"]["a"] = 999
        record = patcher.get_patch(patch_id)
        assert record["original_data"]["nested"]["a"] == 1

    def test_apply_patch_with_label(self):
        patcher = PipelineDataPatcher()
        patch_id = patcher.apply_patch({"x": 1}, {"x": 2}, label="test-label")
        record = patcher.get_patch(patch_id)
        assert record["label"] == "test-label"

    def test_apply_patch_stores_patched_data(self):
        patcher = PipelineDataPatcher()
        patch_id = patcher.apply_patch({"a": 1, "b": 2}, {"b": 20, "c": 30})
        record = patcher.get_patch(patch_id)
        assert record["patched_data"]["a"] == 1
        assert record["patched_data"]["b"] == 20
        assert record["patched_data"]["c"] == 30

    def test_apply_patch_stores_original_data(self):
        patcher = PipelineDataPatcher()
        patch_id = patcher.apply_patch({"a": 1, "b": 2}, {"b": 20})
        record = patcher.get_patch(patch_id)
        assert record["original_data"]["a"] == 1
        assert record["original_data"]["b"] == 2

    def test_apply_patch_stores_keys_patched(self):
        patcher = PipelineDataPatcher()
        patch_id = patcher.apply_patch({"a": 1}, {"b": 2, "c": 3})
        record = patcher.get_patch(patch_id)
        assert sorted(record["keys_patched"]) == ["b", "c"]


class TestGetPatch:
    """get_patch method."""

    def test_get_patch_existing(self):
        patcher = PipelineDataPatcher()
        patch_id = patcher.apply_patch({"a": 1}, {"a": 2})
        result = patcher.get_patch(patch_id)
        assert result is not None
        assert result["patch_id"] == patch_id

    def test_get_patch_nonexistent(self):
        patcher = PipelineDataPatcher()
        assert patcher.get_patch("pdpa-nonexistent") is None

    def test_get_patch_contains_patches_dict(self):
        patcher = PipelineDataPatcher()
        patch_id = patcher.apply_patch({"field": "old"}, {"field": "new"})
        record = patcher.get_patch(patch_id)
        assert record["patches"]["field"] == "new"


class TestGetPatches:
    """get_patches listing."""

    def test_get_patches_returns_list(self):
        patcher = PipelineDataPatcher()
        patcher.apply_patch({"a": 1}, {"a": 2})
        result = patcher.get_patches()
        assert isinstance(result, list)
        assert len(result) == 1

    def test_get_patches_newest_first(self):
        patcher = PipelineDataPatcher()
        id1 = patcher.apply_patch({"order": 1}, {"order": 10})
        id2 = patcher.apply_patch({"order": 2}, {"order": 20})
        results = patcher.get_patches()
        assert results[0]["patch_id"] == id2
        assert results[1]["patch_id"] == id1

    def test_get_patches_filter_by_label(self):
        patcher = PipelineDataPatcher()
        patcher.apply_patch({"x": 1}, {"x": 10}, label="alpha")
        patcher.apply_patch({"x": 2}, {"x": 20}, label="beta")
        patcher.apply_patch({"x": 3}, {"x": 30}, label="alpha")
        results = patcher.get_patches(label="alpha")
        assert len(results) == 2
        assert all(r["label"] == "alpha" for r in results)

    def test_get_patches_respects_limit(self):
        patcher = PipelineDataPatcher()
        for i in range(10):
            patcher.apply_patch({"i": i}, {"i": i * 10})
        results = patcher.get_patches(limit=3)
        assert len(results) == 3

    def test_get_patches_empty(self):
        patcher = PipelineDataPatcher()
        assert patcher.get_patches() == []


class TestRevertPatch:
    """revert_patch method."""

    def test_revert_patch_returns_original(self):
        patcher = PipelineDataPatcher()
        patch_id = patcher.apply_patch({"val": 42}, {"val": 99})
        reverted = patcher.revert_patch(patch_id)
        assert reverted["val"] == 42

    def test_revert_patch_returns_deep_copy(self):
        patcher = PipelineDataPatcher()
        patch_id = patcher.apply_patch({"nested": {"v": 1}}, {"nested": {"v": 2}})
        rev1 = patcher.revert_patch(patch_id)
        rev2 = patcher.revert_patch(patch_id)
        assert rev1 == rev2
        rev1["nested"]["v"] = 0
        rev3 = patcher.revert_patch(patch_id)
        assert rev3["nested"]["v"] == 1

    def test_revert_patch_nonexistent(self):
        patcher = PipelineDataPatcher()
        assert patcher.revert_patch("pdpa-missing") is None


class TestPatchCount:
    """get_patch_count method."""

    def test_count_all(self):
        patcher = PipelineDataPatcher()
        for i in range(5):
            patcher.apply_patch({"i": i}, {"i": i * 10})
        assert patcher.get_patch_count() == 5

    def test_count_by_label(self):
        patcher = PipelineDataPatcher()
        patcher.apply_patch({"x": 1}, {"x": 10}, label="a")
        patcher.apply_patch({"x": 2}, {"x": 20}, label="b")
        patcher.apply_patch({"x": 3}, {"x": 30}, label="a")
        assert patcher.get_patch_count(label="a") == 2
        assert patcher.get_patch_count(label="b") == 1
        assert patcher.get_patch_count(label="c") == 0


class TestStats:
    """get_stats method."""

    def test_stats_empty(self):
        patcher = PipelineDataPatcher()
        stats = patcher.get_stats()
        assert stats["total_patches"] == 0
        assert stats["unique_labels"] == 0
        assert stats["total_keys_patched"] == 0

    def test_stats_populated(self):
        patcher = PipelineDataPatcher()
        patcher.apply_patch({"a": 1}, {"a": 10, "b": 20}, label="x")
        patcher.apply_patch({"c": 3}, {"c": 30}, label="y")
        patcher.apply_patch({"d": 4}, {"d": 40, "e": 50, "f": 60}, label="x")
        stats = patcher.get_stats()
        assert stats["total_patches"] == 3
        assert stats["unique_labels"] == 2
        assert stats["total_keys_patched"] == 6


class TestReset:
    """reset method."""

    def test_reset_clears_entries(self):
        patcher = PipelineDataPatcher()
        patcher.apply_patch({"a": 1}, {"a": 2})
        patcher.apply_patch({"b": 2}, {"b": 3})
        assert patcher.get_patch_count() == 2
        patcher.reset()
        assert patcher.get_patch_count() == 0

    def test_reset_fires_event(self):
        patcher = PipelineDataPatcher()
        events = []
        patcher.on_change = lambda action, data: events.append(action)
        patcher.reset()
        assert "reset" in events


class TestCallbacks:
    """Callback and event system."""

    def test_on_change_fires_on_apply_patch(self):
        patcher = PipelineDataPatcher()
        events = []
        patcher.on_change = lambda action, data: events.append((action, data))
        patcher.apply_patch({"x": 1}, {"x": 2})
        assert len(events) == 1
        assert events[0][0] == "apply_patch"

    def test_on_change_property(self):
        patcher = PipelineDataPatcher()
        assert patcher.on_change is None
        cb = lambda a, d: None
        patcher.on_change = cb
        assert patcher.on_change is cb

    def test_callback_exception_is_silent(self):
        patcher = PipelineDataPatcher()
        patcher.on_change = lambda a, d: (_ for _ in ()).throw(ValueError("boom"))
        patch_id = patcher.apply_patch({"x": 1}, {"x": 2})
        assert patch_id.startswith("pdpa-")

    def test_remove_callback(self):
        patcher = PipelineDataPatcher()
        patcher._callbacks["mycb"] = lambda a, d: None
        assert patcher.remove_callback("mycb") is True
        assert patcher.remove_callback("mycb") is False

    def test_named_callback_fires(self):
        patcher = PipelineDataPatcher()
        fired = []
        patcher._callbacks["tracker"] = lambda a, d: fired.append(a)
        patcher.apply_patch({"v": 1}, {"v": 2})
        assert "apply_patch" in fired

    def test_named_callback_exception_silent(self):
        patcher = PipelineDataPatcher()
        patcher._callbacks["bad"] = lambda a, d: 1 / 0
        patch_id = patcher.apply_patch({"v": 1}, {"v": 2})
        assert patch_id.startswith("pdpa-")


class TestPruning:
    """Eviction when exceeding MAX_ENTRIES."""

    def test_prune_evicts_oldest(self):
        patcher = PipelineDataPatcher()
        patcher.MAX_ENTRIES = 5
        ids = []
        for i in range(7):
            ids.append(patcher.apply_patch({"i": i}, {"i": i * 10}))
        assert patcher.get_patch_count() == 5
        assert patcher.get_patch(ids[0]) is None
        assert patcher.get_patch(ids[1]) is None
        assert patcher.get_patch(ids[6]) is not None
