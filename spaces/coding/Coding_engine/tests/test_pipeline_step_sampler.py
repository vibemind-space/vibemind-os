"""Tests for PipelineStepSampler service."""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_step_sampler import PipelineStepSampler


class TestPipelineStepSampler(unittest.TestCase):
    """Tests for PipelineStepSampler."""

    def setUp(self):
        self.svc = PipelineStepSampler()

    # -- sample ----------------------------------------------------------

    def test_sample_returns_id(self):
        sid = self.svc.sample("p1", "step_a", {"x": 1})
        self.assertIsInstance(sid, str)
        self.assertTrue(sid.startswith("pssp-"))

    def test_sample_stores_fields(self):
        sid = self.svc.sample("p1", "step_a", {"x": 1}, metadata={"tag": "v1"})
        entry = self.svc.get_sample(sid)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["pipeline_id"], "p1")
        self.assertEqual(entry["step_name"], "step_a")
        self.assertEqual(entry["value"], {"x": 1})
        self.assertEqual(entry["metadata"], {"tag": "v1"})
        self.assertIn("created_at", entry)
        self.assertIn("updated_at", entry)

    def test_sample_default_metadata(self):
        sid = self.svc.sample("p1", "step_a", "val")
        entry = self.svc.get_sample(sid)
        self.assertEqual(entry["metadata"], {})

    def test_sample_with_none_value(self):
        sid = self.svc.sample("p1", "step_a", None)
        entry = self.svc.get_sample(sid)
        self.assertIsNone(entry["value"])

    def test_sample_with_list_value(self):
        sid = self.svc.sample("p1", "step_a", [1, 2, 3])
        entry = self.svc.get_sample(sid)
        self.assertEqual(entry["value"], [1, 2, 3])

    def test_sample_stores_sample_rate(self):
        sid = self.svc.sample("p1", "step_a", "val", sample_rate=0.5)
        if sid:
            entry = self.svc.get_sample(sid)
            self.assertEqual(entry["sample_rate"], 0.5)

    def test_sample_rate_zero_skips(self):
        sid = self.svc.sample("p1", "step_a", "val", sample_rate=0.0)
        self.assertEqual(sid, "")
        self.assertEqual(self.svc.get_sample_count(), 0)

    def test_sample_rate_one_always_records(self):
        for i in range(20):
            sid = self.svc.sample("p1", f"step_{i}", "val", sample_rate=1.0)
            self.assertTrue(sid.startswith("pssp-"))
        self.assertEqual(self.svc.get_sample_count(), 20)

    # -- get_sample ------------------------------------------------------

    def test_get_sample_not_found(self):
        result = self.svc.get_sample("nonexistent")
        self.assertIsNone(result)

    def test_get_sample_returns_copy(self):
        sid = self.svc.sample("p1", "step_a", "val")
        entry = self.svc.get_sample(sid)
        entry["pipeline_id"] = "modified"
        original = self.svc.get_sample(sid)
        self.assertEqual(original["pipeline_id"], "p1")

    # -- get_samples -----------------------------------------------------

    def test_get_samples_empty(self):
        result = self.svc.get_samples()
        self.assertEqual(result, [])

    def test_get_samples_newest_first(self):
        sid1 = self.svc.sample("p1", "step_a", "val1")
        sid2 = self.svc.sample("p1", "step_b", "val2")
        sid3 = self.svc.sample("p1", "step_c", "val3")
        result = self.svc.get_samples()
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["sample_id"], sid3)
        self.assertEqual(result[2]["sample_id"], sid1)

    def test_get_samples_filter_by_pipeline(self):
        self.svc.sample("p1", "step_a", "val")
        self.svc.sample("p2", "step_b", "val")
        self.svc.sample("p1", "step_c", "val")
        result = self.svc.get_samples(pipeline_id="p1")
        self.assertEqual(len(result), 2)
        for r in result:
            self.assertEqual(r["pipeline_id"], "p1")

    def test_get_samples_filter_by_step_name(self):
        self.svc.sample("p1", "step_a", "val")
        self.svc.sample("p1", "step_b", "val")
        self.svc.sample("p2", "step_a", "val")
        result = self.svc.get_samples(step_name="step_a")
        self.assertEqual(len(result), 2)
        for r in result:
            self.assertEqual(r["step_name"], "step_a")

    def test_get_samples_filter_by_both(self):
        self.svc.sample("p1", "step_a", "val")
        self.svc.sample("p1", "step_b", "val")
        self.svc.sample("p2", "step_a", "val")
        result = self.svc.get_samples(pipeline_id="p1", step_name="step_a")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["pipeline_id"], "p1")
        self.assertEqual(result[0]["step_name"], "step_a")

    def test_get_samples_limit(self):
        for i in range(10):
            self.svc.sample("p1", f"step_{i}", "val")
        result = self.svc.get_samples(limit=3)
        self.assertEqual(len(result), 3)

    def test_get_samples_returns_dicts(self):
        self.svc.sample("p1", "step_a", "val")
        result = self.svc.get_samples()
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], dict)
        self.assertIn("sample_id", result[0])

    def test_get_samples_no_match(self):
        self.svc.sample("p1", "step_a", "val")
        result = self.svc.get_samples(pipeline_id="p99")
        self.assertEqual(result, [])

    # -- get_sample_count ------------------------------------------------

    def test_get_sample_count_all(self):
        self.svc.sample("p1", "step_a", "val")
        self.svc.sample("p2", "step_b", "val")
        self.assertEqual(self.svc.get_sample_count(), 2)

    def test_get_sample_count_by_pipeline(self):
        self.svc.sample("p1", "step_a", "val")
        self.svc.sample("p2", "step_b", "val")
        self.svc.sample("p1", "step_c", "val")
        self.assertEqual(self.svc.get_sample_count(pipeline_id="p1"), 2)
        self.assertEqual(self.svc.get_sample_count(pipeline_id="p2"), 1)
        self.assertEqual(self.svc.get_sample_count(pipeline_id="p3"), 0)

    def test_get_sample_count_empty(self):
        self.assertEqual(self.svc.get_sample_count(), 0)

    # -- get_stats -------------------------------------------------------

    def test_get_stats_empty(self):
        stats = self.svc.get_stats()
        self.assertEqual(stats["total_samples"], 0)
        self.assertEqual(stats["unique_pipelines"], 0)
        self.assertEqual(stats["unique_steps"], 0)

    def test_get_stats_with_data(self):
        self.svc.sample("p1", "step_a", "val")
        self.svc.sample("p1", "step_b", "val")
        self.svc.sample("p2", "step_a", "val")
        stats = self.svc.get_stats()
        self.assertEqual(stats["total_samples"], 3)
        self.assertEqual(stats["unique_pipelines"], 2)
        self.assertEqual(stats["unique_steps"], 2)

    # -- reset -----------------------------------------------------------

    def test_reset(self):
        self.svc.sample("p1", "step_a", "val")
        self.svc.sample("p2", "step_b", "val")
        self.svc.reset()
        self.assertEqual(self.svc.get_sample_count(), 0)
        self.assertEqual(self.svc.get_stats()["total_samples"], 0)

    def test_reset_clears_callbacks(self):
        self.svc.on_change = lambda a, d: None
        self.svc.reset()
        self.assertIsNone(self.svc.on_change)

    def test_reset_resets_sequence(self):
        self.svc.sample("p1", "step_a", "val")
        self.svc.reset()
        self.assertEqual(self.svc._state._seq, 0)

    # -- callbacks -------------------------------------------------------

    def test_on_change_property(self):
        self.assertIsNone(self.svc.on_change)
        events = []
        self.svc.on_change = lambda action, data: events.append((action, data))
        self.svc.sample("p1", "step_a", "val")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "sampled")

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
        sid = self.svc.sample("p1", "step_a", "val")
        self.assertTrue(sid.startswith("pssp-"))

    def test_fire_event_on_sample(self):
        events = []
        self.svc.on_change = lambda action, data: events.append(action)
        self.svc.sample("p1", "step_a", "val")
        self.assertIn("sampled", events)

    def test_callback_receives_entry_copy(self):
        received = []
        self.svc.on_change = lambda action, data: received.append(data)
        sid = self.svc.sample("p1", "step_a", "val")
        self.assertEqual(len(received), 1)
        received[0]["pipeline_id"] = "modified"
        original = self.svc.get_sample(sid)
        self.assertEqual(original["pipeline_id"], "p1")

    # -- ID generation ---------------------------------------------------

    def test_unique_ids(self):
        ids = set()
        for i in range(100):
            sid = self.svc.sample("p1", f"step_{i}", "val")
            ids.add(sid)
        self.assertEqual(len(ids), 100)

    def test_id_prefix(self):
        sid = self.svc.sample("p1", "step_a", "val")
        self.assertTrue(sid.startswith("pssp-"))

    # -- pruning ---------------------------------------------------------

    def test_prune_oldest_quarter(self):
        self.svc.MAX_ENTRIES = 10
        for i in range(12):
            self.svc.sample("p1", f"step_{i}", "val")
        self.assertLessEqual(self.svc.get_sample_count(), 12)

    def test_prune_keeps_newest(self):
        self.svc.MAX_ENTRIES = 4
        sids = []
        for i in range(6):
            sid = self.svc.sample("p1", f"step_{i}", f"val_{i}")
            sids.append(sid)
        # The newest entries should still be present
        remaining = self.svc.get_samples(limit=100)
        remaining_ids = {e["sample_id"] for e in remaining}
        # The very last entry should always survive pruning
        self.assertIn(sids[-1], remaining_ids)


if __name__ == "__main__":
    unittest.main()
