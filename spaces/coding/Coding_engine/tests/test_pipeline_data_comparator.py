"""Tests for pipeline_data_comparator module."""

from __future__ import annotations

import sys
import os
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_data_comparator import PipelineDataComparator, PipelineDataComparatorState


class TestPipelineDataComparator(unittest.TestCase):
    """Test suite for PipelineDataComparator."""

    def setUp(self):
        self.comp = PipelineDataComparator()

    # --- Initialization ---

    def test_initial_state(self):
        stats = self.comp.get_stats()
        self.assertEqual(stats["total_comparisons"], 0)
        self.assertEqual(stats["pipeline_count"], 0)
        self.assertEqual(stats["callbacks_registered"], 0)

    def test_initial_state_dataclass(self):
        state = PipelineDataComparatorState()
        self.assertEqual(state.entries, {})
        self.assertEqual(state._seq, 0)

    def test_initial_comparisons_empty(self):
        self.assertEqual(self.comp.get_comparisons(), [])

    def test_initial_comparison_count_zero(self):
        self.assertEqual(self.comp.get_comparison_count(), 0)

    # --- Compare basics ---

    def test_compare_returns_id(self):
        comp_id = self.comp.compare("pipe-1", {"a": 1}, {"a": 2})
        self.assertTrue(comp_id.startswith("pdcm-"))
        self.assertEqual(len(comp_id), 5 + 16)

    def test_compare_identical_data(self):
        data = {"x": 1, "y": 2}
        comp_id = self.comp.compare("pipe-1", data, data)
        result = self.comp.get_comparison(comp_id)
        self.assertTrue(result["identical"])
        self.assertEqual(result["diff_count"], 0)
        self.assertEqual(result["diffs"], [])

    def test_compare_different_data(self):
        comp_id = self.comp.compare("pipe-1", {"a": 1}, {"a": 2})
        result = self.comp.get_comparison(comp_id)
        self.assertFalse(result["identical"])
        self.assertEqual(result["diff_count"], 1)
        self.assertEqual(result["diffs"][0]["type"], "changed")
        self.assertEqual(result["diffs"][0]["old"], 1)
        self.assertEqual(result["diffs"][0]["new"], 2)

    def test_compare_added_keys(self):
        comp_id = self.comp.compare("pipe-1", {"a": 1}, {"a": 1, "b": 2})
        result = self.comp.get_comparison(comp_id)
        added = [d for d in result["diffs"] if d["type"] == "added"]
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0]["key"], "b")
        self.assertEqual(added[0]["value"], 2)

    def test_compare_removed_keys(self):
        comp_id = self.comp.compare("pipe-1", {"a": 1, "b": 2}, {"a": 1})
        result = self.comp.get_comparison(comp_id)
        removed = [d for d in result["diffs"] if d["type"] == "removed"]
        self.assertEqual(len(removed), 1)
        self.assertEqual(removed[0]["key"], "b")

    def test_compare_non_dict_data(self):
        comp_id = self.comp.compare("pipe-1", [1, 2, 3], [4, 5, 6])
        result = self.comp.get_comparison(comp_id)
        self.assertFalse(result["identical"])
        self.assertEqual(result["diffs"][0]["type"], "replaced")

    def test_compare_non_dict_identical(self):
        comp_id = self.comp.compare("pipe-1", "hello", "hello")
        result = self.comp.get_comparison(comp_id)
        self.assertTrue(result["identical"])

    def test_compare_with_label(self):
        comp_id = self.comp.compare("pipe-1", {"a": 1}, {"a": 2}, label="test-run")
        result = self.comp.get_comparison(comp_id)
        self.assertEqual(result["label"], "test-run")

    def test_compare_without_label(self):
        comp_id = self.comp.compare("pipe-1", {"a": 1}, {"a": 2})
        result = self.comp.get_comparison(comp_id)
        self.assertEqual(result["label"], "")

    # --- get_comparison ---

    def test_get_comparison_not_found(self):
        self.assertIsNone(self.comp.get_comparison("pdcm-nonexistent"))

    def test_get_comparison_returns_copy(self):
        comp_id = self.comp.compare("pipe-1", {"a": 1}, {"a": 2})
        r1 = self.comp.get_comparison(comp_id)
        r2 = self.comp.get_comparison(comp_id)
        self.assertEqual(r1, r2)
        self.assertIsNot(r1, r2)

    # --- get_comparisons ---

    def test_get_comparisons_all(self):
        self.comp.compare("pipe-1", {"a": 1}, {"a": 2})
        self.comp.compare("pipe-2", {"b": 1}, {"b": 2})
        results = self.comp.get_comparisons()
        self.assertEqual(len(results), 2)

    def test_get_comparisons_by_pipeline(self):
        self.comp.compare("pipe-1", {"a": 1}, {"a": 2})
        self.comp.compare("pipe-2", {"b": 1}, {"b": 2})
        self.comp.compare("pipe-1", {"c": 1}, {"c": 2})
        results = self.comp.get_comparisons(pipeline_id="pipe-1")
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r["pipeline_id"], "pipe-1")

    def test_get_comparisons_limit(self):
        for i in range(10):
            self.comp.compare("pipe-1", {"v": i}, {"v": i + 1})
        results = self.comp.get_comparisons(limit=3)
        self.assertEqual(len(results), 3)

    def test_get_comparisons_sorted_desc(self):
        self.comp.compare("pipe-1", {"a": 1}, {"a": 2})
        self.comp.compare("pipe-1", {"b": 1}, {"b": 2})
        results = self.comp.get_comparisons()
        self.assertGreaterEqual(results[0]["created_at"], results[1]["created_at"])

    def test_get_comparisons_returns_copies(self):
        self.comp.compare("pipe-1", {"a": 1}, {"a": 2})
        r1 = self.comp.get_comparisons()
        r2 = self.comp.get_comparisons()
        self.assertIsNot(r1[0], r2[0])

    # --- get_comparison_count ---

    def test_get_comparison_count_all(self):
        self.comp.compare("pipe-1", {}, {})
        self.comp.compare("pipe-2", {}, {})
        self.assertEqual(self.comp.get_comparison_count(), 2)

    def test_get_comparison_count_by_pipeline(self):
        self.comp.compare("pipe-1", {}, {})
        self.comp.compare("pipe-2", {}, {})
        self.comp.compare("pipe-1", {}, {})
        self.assertEqual(self.comp.get_comparison_count(pipeline_id="pipe-1"), 2)
        self.assertEqual(self.comp.get_comparison_count(pipeline_id="pipe-2"), 1)

    def test_get_comparison_count_empty_pipeline(self):
        self.assertEqual(self.comp.get_comparison_count(pipeline_id="nonexistent"), 0)

    # --- Callbacks ---

    def test_register_and_fire_callback(self):
        events = []
        self.comp.register_callback("test_cb", lambda e: events.append(e))
        self.comp.compare("pipe-1", {"a": 1}, {"a": 2})
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["action"], "compare")
        self.assertEqual(events[0]["data"]["pipeline_id"], "pipe-1")

    def test_remove_callback(self):
        self.comp.register_callback("test_cb", lambda e: None)
        self.assertTrue(self.comp.remove_callback("test_cb"))

    def test_remove_callback_not_found(self):
        self.assertFalse(self.comp.remove_callback("nonexistent"))

    def test_callback_error_does_not_raise(self):
        def bad_callback(e):
            raise ValueError("boom")
        self.comp.register_callback("bad", bad_callback)
        comp_id = self.comp.compare("pipe-1", {"a": 1}, {"a": 2})
        self.assertIsNotNone(comp_id)

    def test_on_change_property(self):
        self.assertIsNotNone(self.comp.on_change)
        self.assertTrue(callable(self.comp.on_change))

    # --- get_stats ---

    def test_get_stats_after_comparisons(self):
        self.comp.compare("pipe-1", {}, {})
        self.comp.compare("pipe-2", {}, {})
        self.comp.register_callback("cb1", lambda e: None)
        stats = self.comp.get_stats()
        self.assertEqual(stats["total_comparisons"], 2)
        self.assertEqual(stats["pipeline_count"], 2)
        self.assertEqual(stats["callbacks_registered"], 1)

    # --- reset ---

    def test_reset(self):
        self.comp.compare("pipe-1", {"a": 1}, {"a": 2})
        self.comp.register_callback("cb", lambda e: None)
        self.comp.reset()
        self.assertEqual(self.comp.get_comparison_count(), 0)
        self.assertEqual(self.comp.get_stats()["callbacks_registered"], 0)
        self.assertEqual(self.comp.get_comparisons(), [])

    # --- Pruning ---

    def test_prune_oldest_quarter(self):
        self.comp.MAX_ENTRIES = 20
        for i in range(25):
            self.comp.compare(f"pipe-{i}", {"v": i}, {"v": i + 1})
        self.assertLessEqual(self.comp.get_comparison_count(), 20)

    # --- ID generation ---

    def test_unique_ids(self):
        ids = set()
        for i in range(50):
            comp_id = self.comp.compare("pipe-1", {"v": i}, {"v": i + 1})
            ids.add(comp_id)
        self.assertEqual(len(ids), 50)

    def test_id_prefix(self):
        comp_id = self.comp.compare("pipe-1", {}, {})
        self.assertTrue(comp_id.startswith("pdcm-"))

    # --- Edge cases ---

    def test_compare_empty_dicts(self):
        comp_id = self.comp.compare("pipe-1", {}, {})
        result = self.comp.get_comparison(comp_id)
        self.assertTrue(result["identical"])

    def test_compare_nested_dicts(self):
        comp_id = self.comp.compare("pipe-1", {"a": {"x": 1}}, {"a": {"x": 2}})
        result = self.comp.get_comparison(comp_id)
        self.assertFalse(result["identical"])
        self.assertEqual(result["diffs"][0]["type"], "changed")

    def test_stores_data_snapshots(self):
        comp_id = self.comp.compare("pipe-1", {"a": 1}, {"b": 2})
        result = self.comp.get_comparison(comp_id)
        self.assertEqual(result["data_a"], {"a": 1})
        self.assertEqual(result["data_b"], {"b": 2})

    def test_pipeline_id_in_entry(self):
        comp_id = self.comp.compare("my-pipeline", {}, {})
        result = self.comp.get_comparison(comp_id)
        self.assertEqual(result["pipeline_id"], "my-pipeline")


if __name__ == "__main__":
    unittest.main()
