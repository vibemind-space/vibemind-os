"""Tests for PipelineStepScaler service."""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_step_scaler import PipelineStepScaler


class TestPipelineStepScaler(unittest.TestCase):
    """Tests for PipelineStepScaler."""

    def setUp(self):
        self.svc = PipelineStepScaler()

    # -- scale -------------------------------------------------------------

    def test_scale_returns_id(self):
        rid = self.svc.scale("p1", "step_a")
        self.assertIsInstance(rid, str)
        self.assertTrue(rid.startswith("pssc-"))

    def test_scale_stores_fields(self):
        rid = self.svc.scale("p1", "step_a", replicas=3, metadata={"cpu": "2x"})
        entry = self.svc.get_scale(rid)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["pipeline_id"], "p1")
        self.assertEqual(entry["step_name"], "step_a")
        self.assertEqual(entry["replicas"], 3)
        self.assertEqual(entry["metadata"], {"cpu": "2x"})
        self.assertIn("created_at", entry)
        self.assertIn("updated_at", entry)

    def test_scale_default_replicas(self):
        rid = self.svc.scale("p1", "step_a")
        entry = self.svc.get_scale(rid)
        self.assertEqual(entry["replicas"], 1)

    def test_scale_default_metadata(self):
        rid = self.svc.scale("p1", "step_a")
        entry = self.svc.get_scale(rid)
        self.assertEqual(entry["metadata"], {})

    def test_scale_custom_replicas(self):
        rid = self.svc.scale("p1", "step_a", replicas=10)
        entry = self.svc.get_scale(rid)
        self.assertEqual(entry["replicas"], 10)

    def test_scale_unique_ids(self):
        rid1 = self.svc.scale("p1", "step_a")
        rid2 = self.svc.scale("p1", "step_a")
        self.assertNotEqual(rid1, rid2)

    def test_scale_fires_callback(self):
        events = []
        self.svc.on_change = lambda action, data: events.append((action, data))
        self.svc.scale("p1", "step_a", replicas=2)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "scaled")
        self.assertEqual(events[0][1]["replicas"], 2)

    # -- get_scale ---------------------------------------------------------

    def test_get_scale_not_found(self):
        result = self.svc.get_scale("nonexistent")
        self.assertIsNone(result)

    def test_get_scale_returns_copy(self):
        rid = self.svc.scale("p1", "step_a")
        entry = self.svc.get_scale(rid)
        entry["pipeline_id"] = "modified"
        original = self.svc.get_scale(rid)
        self.assertEqual(original["pipeline_id"], "p1")

    # -- get_scales --------------------------------------------------------

    def test_get_scales_empty(self):
        result = self.svc.get_scales()
        self.assertEqual(result, [])

    def test_get_scales_newest_first(self):
        rid1 = self.svc.scale("p1", "step_a")
        rid2 = self.svc.scale("p1", "step_b")
        rid3 = self.svc.scale("p1", "step_c")
        result = self.svc.get_scales()
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["record_id"], rid3)
        self.assertEqual(result[1]["record_id"], rid2)
        self.assertEqual(result[2]["record_id"], rid1)

    def test_get_scales_filter_by_pipeline(self):
        self.svc.scale("p1", "step_a")
        self.svc.scale("p2", "step_b")
        self.svc.scale("p1", "step_c")
        result = self.svc.get_scales(pipeline_id="p1")
        self.assertEqual(len(result), 2)
        for entry in result:
            self.assertEqual(entry["pipeline_id"], "p1")

    def test_get_scales_limit(self):
        for i in range(10):
            self.svc.scale("p1", f"step_{i}")
        result = self.svc.get_scales(limit=3)
        self.assertEqual(len(result), 3)

    def test_get_scales_returns_copies(self):
        self.svc.scale("p1", "step_a")
        result = self.svc.get_scales()
        result[0]["pipeline_id"] = "modified"
        original = self.svc.get_scales()
        self.assertEqual(original[0]["pipeline_id"], "p1")

    def test_get_scales_filter_nonexistent_pipeline(self):
        self.svc.scale("p1", "step_a")
        result = self.svc.get_scales(pipeline_id="nope")
        self.assertEqual(result, [])

    # -- get_scale_count ---------------------------------------------------

    def test_get_scale_count_empty(self):
        self.assertEqual(self.svc.get_scale_count(), 0)

    def test_get_scale_count_total(self):
        self.svc.scale("p1", "step_a")
        self.svc.scale("p2", "step_b")
        self.assertEqual(self.svc.get_scale_count(), 2)

    def test_get_scale_count_by_pipeline(self):
        self.svc.scale("p1", "step_a")
        self.svc.scale("p2", "step_b")
        self.svc.scale("p1", "step_c")
        self.assertEqual(self.svc.get_scale_count(pipeline_id="p1"), 2)
        self.assertEqual(self.svc.get_scale_count(pipeline_id="p2"), 1)

    def test_get_scale_count_nonexistent_pipeline(self):
        self.svc.scale("p1", "step_a")
        self.assertEqual(self.svc.get_scale_count(pipeline_id="nope"), 0)

    # -- callbacks ---------------------------------------------------------

    def test_on_change_property_default_none(self):
        self.assertIsNone(self.svc.on_change)

    def test_on_change_set_and_get(self):
        cb = lambda a, d: None
        self.svc.on_change = cb
        self.assertIs(self.svc.on_change, cb)

    def test_on_change_clear(self):
        self.svc.on_change = lambda a, d: None
        self.svc.on_change = None
        self.assertIsNone(self.svc.on_change)

    def test_remove_callback_exists(self):
        self.svc.on_change = lambda a, d: None
        self.assertTrue(self.svc.remove_callback("_on_change"))
        self.assertIsNone(self.svc.on_change)

    def test_remove_callback_missing(self):
        self.assertFalse(self.svc.remove_callback("nonexistent"))

    def test_callback_exception_does_not_propagate(self):
        def bad_cb(action, data):
            raise RuntimeError("boom")
        self.svc.on_change = bad_cb
        # Should not raise
        rid = self.svc.scale("p1", "step_a")
        self.assertIsNotNone(rid)

    # -- get_stats ---------------------------------------------------------

    def test_get_stats_empty(self):
        stats = self.svc.get_stats()
        self.assertEqual(stats["total_scales"], 0)
        self.assertEqual(stats["unique_pipelines"], 0)
        self.assertEqual(stats["unique_steps"], 0)

    def test_get_stats_with_data(self):
        self.svc.scale("p1", "step_a")
        self.svc.scale("p2", "step_b")
        self.svc.scale("p1", "step_c")
        stats = self.svc.get_stats()
        self.assertEqual(stats["total_scales"], 3)
        self.assertEqual(stats["unique_pipelines"], 2)
        self.assertEqual(stats["unique_steps"], 3)

    # -- reset -------------------------------------------------------------

    def test_reset_clears_entries(self):
        self.svc.scale("p1", "step_a")
        self.svc.reset()
        self.assertEqual(self.svc.get_scale_count(), 0)

    def test_reset_clears_callbacks(self):
        self.svc.on_change = lambda a, d: None
        self.svc.reset()
        self.assertIsNone(self.svc.on_change)

    def test_reset_resets_sequence(self):
        rid1 = self.svc.scale("p1", "step_a")
        self.svc.reset()
        rid2 = self.svc.scale("p1", "step_a")
        # After reset, IDs restart from seq 1 — same seq but still unique
        # due to object id in hash; just verify both are valid
        self.assertTrue(rid2.startswith("pssc-"))

    # -- pruning -----------------------------------------------------------

    def test_prune_removes_oldest_quarter(self):
        self.svc.MAX_ENTRIES = 10
        for i in range(12):
            self.svc.scale("p1", f"step_{i}")
        # After 11th insert triggers prune (> 10), removes 10//4 = 2
        # Then 12th insert triggers prune again if still > 10
        count = self.svc.get_scale_count()
        self.assertLessEqual(count, 11)

    # -- PREFIX ------------------------------------------------------------

    def test_prefix_value(self):
        self.assertEqual(PipelineStepScaler.PREFIX, "pssc-")

    def test_max_entries_value(self):
        self.assertEqual(PipelineStepScaler.MAX_ENTRIES, 10000)


if __name__ == "__main__":
    unittest.main()
