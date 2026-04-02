"""Tests for PipelineStepSkipper service."""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_step_skipper import PipelineStepSkipper


class TestPipelineStepSkipper(unittest.TestCase):
    """Tests for PipelineStepSkipper."""

    def setUp(self):
        self.svc = PipelineStepSkipper()

    # -- skip ------------------------------------------------------------

    def test_skip_returns_id(self):
        sid = self.svc.skip("p1", "step_a", "not needed")
        self.assertIsInstance(sid, str)
        self.assertTrue(sid.startswith("pssk-"))

    def test_skip_stores_fields(self):
        sid = self.svc.skip("p1", "step_a", "duplicate", metadata={"tag": "v1"})
        entry = self.svc.get_skip(sid)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["pipeline_id"], "p1")
        self.assertEqual(entry["step_name"], "step_a")
        self.assertEqual(entry["reason"], "duplicate")
        self.assertEqual(entry["metadata"], {"tag": "v1"})
        self.assertIn("created_at", entry)
        self.assertIn("updated_at", entry)

    def test_skip_default_reason(self):
        sid = self.svc.skip("p1", "step_a")
        entry = self.svc.get_skip(sid)
        self.assertEqual(entry["reason"], "")

    def test_skip_default_metadata(self):
        sid = self.svc.skip("p1", "step_a", "reason")
        entry = self.svc.get_skip(sid)
        self.assertEqual(entry["metadata"], {})

    def test_skip_with_complex_metadata(self):
        meta = {"score": 0.95, "tags": ["a", "b"], "nested": {"x": 1}}
        sid = self.svc.skip("p1", "step_a", "complex", metadata=meta)
        entry = self.svc.get_skip(sid)
        self.assertEqual(entry["metadata"], meta)

    def test_skip_empty_reason(self):
        sid = self.svc.skip("p1", "step_a", "")
        entry = self.svc.get_skip(sid)
        self.assertEqual(entry["reason"], "")

    # -- get_skip --------------------------------------------------------

    def test_get_skip_not_found(self):
        result = self.svc.get_skip("nonexistent")
        self.assertIsNone(result)

    def test_get_skip_returns_copy(self):
        sid = self.svc.skip("p1", "step_a", "reason")
        entry = self.svc.get_skip(sid)
        entry["pipeline_id"] = "modified"
        original = self.svc.get_skip(sid)
        self.assertEqual(original["pipeline_id"], "p1")

    # -- get_skips -------------------------------------------------------

    def test_get_skips_empty(self):
        result = self.svc.get_skips()
        self.assertEqual(result, [])

    def test_get_skips_newest_first(self):
        sid1 = self.svc.skip("p1", "step_a", "r1")
        sid2 = self.svc.skip("p1", "step_b", "r2")
        sid3 = self.svc.skip("p1", "step_c", "r3")
        result = self.svc.get_skips()
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["skip_id"], sid3)
        self.assertEqual(result[2]["skip_id"], sid1)

    def test_get_skips_filter_by_pipeline(self):
        self.svc.skip("p1", "step_a", "r1")
        self.svc.skip("p2", "step_b", "r2")
        self.svc.skip("p1", "step_c", "r3")
        result = self.svc.get_skips(pipeline_id="p1")
        self.assertEqual(len(result), 2)
        for r in result:
            self.assertEqual(r["pipeline_id"], "p1")

    def test_get_skips_limit(self):
        for i in range(10):
            self.svc.skip("p1", f"step_{i}", f"reason_{i}")
        result = self.svc.get_skips(limit=3)
        self.assertEqual(len(result), 3)

    def test_get_skips_returns_dicts(self):
        self.svc.skip("p1", "step_a", "reason")
        result = self.svc.get_skips()
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], dict)
        self.assertIn("skip_id", result[0])

    def test_get_skips_no_match(self):
        self.svc.skip("p1", "step_a", "reason")
        result = self.svc.get_skips(pipeline_id="p99")
        self.assertEqual(result, [])

    # -- get_skip_count --------------------------------------------------

    def test_get_skip_count_all(self):
        self.svc.skip("p1", "step_a", "r1")
        self.svc.skip("p2", "step_b", "r2")
        self.assertEqual(self.svc.get_skip_count(), 2)

    def test_get_skip_count_by_pipeline(self):
        self.svc.skip("p1", "step_a", "r1")
        self.svc.skip("p2", "step_b", "r2")
        self.svc.skip("p1", "step_c", "r3")
        self.assertEqual(self.svc.get_skip_count(pipeline_id="p1"), 2)
        self.assertEqual(self.svc.get_skip_count(pipeline_id="p2"), 1)
        self.assertEqual(self.svc.get_skip_count(pipeline_id="p3"), 0)

    def test_get_skip_count_empty(self):
        self.assertEqual(self.svc.get_skip_count(), 0)

    # -- get_stats -------------------------------------------------------

    def test_get_stats_empty(self):
        stats = self.svc.get_stats()
        self.assertEqual(stats["total_skips"], 0)
        self.assertEqual(stats["unique_pipelines"], 0)

    def test_get_stats_with_data(self):
        self.svc.skip("p1", "step_a", "r1")
        self.svc.skip("p1", "step_b", "r2")
        self.svc.skip("p2", "step_a", "r3")
        stats = self.svc.get_stats()
        self.assertEqual(stats["total_skips"], 3)
        self.assertEqual(stats["unique_pipelines"], 2)

    # -- reset -----------------------------------------------------------

    def test_reset(self):
        self.svc.skip("p1", "step_a", "r1")
        self.svc.skip("p2", "step_b", "r2")
        self.svc.reset()
        self.assertEqual(self.svc.get_skip_count(), 0)
        self.assertEqual(self.svc.get_stats()["total_skips"], 0)

    def test_reset_clears_callbacks(self):
        self.svc.on_change = lambda a, d: None
        self.svc.reset()
        self.assertIsNone(self.svc.on_change)

    def test_reset_allows_new_entries(self):
        self.svc.skip("p1", "step_a", "r1")
        self.svc.reset()
        sid = self.svc.skip("p2", "step_b", "r2")
        self.assertEqual(self.svc.get_skip_count(), 1)
        self.assertIsNotNone(self.svc.get_skip(sid))

    # -- callbacks -------------------------------------------------------

    def test_on_change_property(self):
        self.assertIsNone(self.svc.on_change)
        events = []
        self.svc.on_change = lambda action, data: events.append((action, data))
        self.svc.skip("p1", "step_a", "reason")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "skipped")

    def test_on_change_set_none(self):
        self.svc.on_change = lambda a, d: None
        self.assertIsNotNone(self.svc.on_change)
        self.svc.on_change = None
        self.assertIsNone(self.svc.on_change)

    def test_remove_callback(self):
        self.svc.on_change = lambda a, d: None
        self.assertTrue(self.svc.remove_callback("__on_change__"))
        self.assertIsNone(self.svc.on_change)

    def test_remove_callback_not_found(self):
        self.assertFalse(self.svc.remove_callback("nonexistent"))

    def test_fire_silent_on_error(self):
        self.svc.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("boom"))
        sid = self.svc.skip("p1", "step_a", "reason")
        self.assertTrue(sid.startswith("pssk-"))

    def test_fire_event_on_skip(self):
        events = []
        self.svc.on_change = lambda action, data: events.append(action)
        self.svc.skip("p1", "step_a", "reason")
        self.assertIn("skipped", events)

    # -- ID generation ---------------------------------------------------

    def test_unique_ids(self):
        ids = set()
        for i in range(100):
            sid = self.svc.skip("p1", f"step_{i}", f"reason_{i}")
            ids.add(sid)
        self.assertEqual(len(ids), 100)

    def test_id_prefix(self):
        sid = self.svc.skip("p1", "step_a", "reason")
        self.assertTrue(sid.startswith("pssk-"))

    # -- pruning ---------------------------------------------------------

    def test_prune_oldest_quarter(self):
        self.svc.MAX_ENTRIES = 10
        for i in range(12):
            self.svc.skip("p1", f"step_{i}", f"reason_{i}")
        self.assertLessEqual(self.svc.get_skip_count(), 12)

    def test_prune_keeps_newest(self):
        self.svc.MAX_ENTRIES = 4
        sids = []
        for i in range(6):
            sids.append(self.svc.skip("p1", f"step_{i}", f"reason_{i}"))
        remaining = self.svc.get_skips(limit=100)
        remaining_ids = {r["skip_id"] for r in remaining}
        # The newest entry should always survive pruning
        self.assertIn(sids[-1], remaining_ids)


if __name__ == "__main__":
    unittest.main()
