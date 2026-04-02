"""Tests for PipelineStepDeduper."""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_step_deduper import PipelineStepDeduper, PipelineStepDeduperState


class TestPipelineStepDeduper(unittest.TestCase):

    def setUp(self):
        self.d = PipelineStepDeduper()

    # --- dedup ---

    def test_dedup_returns_id_with_prefix(self):
        rid = self.d.dedup("pipe1", "step_a", "hash1")
        self.assertTrue(rid.startswith("psdd-"))
        self.assertEqual(len(rid), 5 + 16)

    def test_dedup_creates_entry(self):
        rid = self.d.dedup("pipe1", "step_a", "hash1")
        entry = self.d.get_dedup(rid)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["pipeline_id"], "pipe1")
        self.assertEqual(entry["step_name"], "step_a")
        self.assertEqual(entry["content_hash"], "hash1")

    def test_dedup_with_metadata(self):
        rid = self.d.dedup("pipe1", "step_a", "hash1", metadata={"key": "val"})
        entry = self.d.get_dedup(rid)
        self.assertEqual(entry["metadata"], {"key": "val"})

    def test_dedup_without_metadata_defaults_empty(self):
        rid = self.d.dedup("pipe1", "step_a", "hash1")
        entry = self.d.get_dedup(rid)
        self.assertEqual(entry["metadata"], {})

    def test_dedup_unique_ids(self):
        ids = set()
        for i in range(50):
            ids.add(self.d.dedup("pipe1", f"step_{i}", f"hash_{i}"))
        self.assertEqual(len(ids), 50)

    def test_dedup_same_inputs_different_ids(self):
        r1 = self.d.dedup("pipe1", "step_a", "hash1")
        r2 = self.d.dedup("pipe1", "step_a", "hash1")
        self.assertNotEqual(r1, r2)

    def test_dedup_entry_has_created_at(self):
        rid = self.d.dedup("pipe1", "step_a", "hash1")
        entry = self.d.get_dedup(rid)
        self.assertIn("created_at", entry)
        self.assertIsInstance(entry["created_at"], float)

    def test_dedup_entry_has_seq(self):
        rid = self.d.dedup("pipe1", "step_a", "hash1")
        entry = self.d.get_dedup(rid)
        self.assertIn("_seq", entry)

    # --- get_dedup ---

    def test_get_dedup_not_found_returns_none(self):
        result = self.d.get_dedup("psdd-nonexistent12345")
        self.assertIsNone(result)

    def test_get_dedup_returns_copy(self):
        rid = self.d.dedup("pipe1", "step_a", "hash1")
        e1 = self.d.get_dedup(rid)
        e2 = self.d.get_dedup(rid)
        self.assertIsNot(e1, e2)
        self.assertEqual(e1, e2)

    # --- get_dedups ---

    def test_get_dedups_all(self):
        self.d.dedup("pipe1", "s1", "h1")
        self.d.dedup("pipe2", "s2", "h2")
        self.d.dedup("pipe1", "s3", "h3")
        results = self.d.get_dedups()
        self.assertEqual(len(results), 3)

    def test_get_dedups_filtered_by_pipeline(self):
        self.d.dedup("pipe1", "s1", "h1")
        self.d.dedup("pipe2", "s2", "h2")
        self.d.dedup("pipe1", "s3", "h3")
        results = self.d.get_dedups(pipeline_id="pipe1")
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r["pipeline_id"] == "pipe1" for r in results))

    def test_get_dedups_sorted_desc_by_created_at(self):
        self.d.dedup("pipe1", "s1", "h1")
        self.d.dedup("pipe1", "s2", "h2")
        self.d.dedup("pipe1", "s3", "h3")
        results = self.d.get_dedups()
        timestamps = [r["created_at"] for r in results]
        seqs = [r["_seq"] for r in results]
        # Should be descending by (created_at, _seq)
        pairs = list(zip(timestamps, seqs))
        self.assertEqual(pairs, sorted(pairs, reverse=True))

    def test_get_dedups_limit(self):
        for i in range(10):
            self.d.dedup("pipe1", f"s{i}", f"h{i}")
        results = self.d.get_dedups(limit=3)
        self.assertEqual(len(results), 3)

    def test_get_dedups_default_limit_50(self):
        for i in range(60):
            self.d.dedup("pipe1", f"s{i}", f"h{i}")
        results = self.d.get_dedups()
        self.assertEqual(len(results), 50)

    def test_get_dedups_returns_copies(self):
        self.d.dedup("pipe1", "s1", "h1")
        r1 = self.d.get_dedups()
        r2 = self.d.get_dedups()
        self.assertIsNot(r1[0], r2[0])

    # --- get_dedup_count ---

    def test_get_dedup_count_empty(self):
        self.assertEqual(self.d.get_dedup_count(), 0)

    def test_get_dedup_count_all(self):
        self.d.dedup("pipe1", "s1", "h1")
        self.d.dedup("pipe2", "s2", "h2")
        self.assertEqual(self.d.get_dedup_count(), 2)

    def test_get_dedup_count_filtered(self):
        self.d.dedup("pipe1", "s1", "h1")
        self.d.dedup("pipe2", "s2", "h2")
        self.d.dedup("pipe1", "s3", "h3")
        self.assertEqual(self.d.get_dedup_count(pipeline_id="pipe1"), 2)
        self.assertEqual(self.d.get_dedup_count(pipeline_id="pipe2"), 1)
        self.assertEqual(self.d.get_dedup_count(pipeline_id="pipe99"), 0)

    # --- callbacks ---

    def test_on_change_property(self):
        events = []
        self.d.on_change = lambda e, data: events.append(e)
        self.d.dedup("pipe1", "s1", "h1")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0], "dedup_created")

    def test_on_change_getter(self):
        self.assertIsNone(self.d.on_change)
        cb = lambda e, d: None
        self.d.on_change = cb
        self.assertIs(self.d.on_change, cb)

    def test_callbacks_fire(self):
        events = []
        self.d._callbacks["my_cb"] = lambda e, data: events.append(e)
        self.d.dedup("pipe1", "s1", "h1")
        self.assertEqual(len(events), 1)

    def test_remove_callback(self):
        self.d._callbacks["my_cb"] = lambda e, data: None
        self.assertTrue(self.d.remove_callback("my_cb"))
        self.assertFalse(self.d.remove_callback("my_cb"))

    def test_remove_callback_stops_firing(self):
        events = []
        self.d._callbacks["my_cb"] = lambda e, data: events.append(e)
        self.d.dedup("pipe1", "s1", "h1")
        self.d.remove_callback("my_cb")
        self.d.dedup("pipe1", "s2", "h2")
        self.assertEqual(len(events), 1)

    def test_callback_exception_handled(self):
        def bad_cb(event, data):
            raise ValueError("boom")
        self.d._callbacks["bad"] = bad_cb
        rid = self.d.dedup("pipe1", "s1", "h1")
        self.assertTrue(rid.startswith("psdd-"))

    def test_on_change_exception_handled(self):
        def bad_on_change(event, data):
            raise RuntimeError("fail")
        self.d.on_change = bad_on_change
        rid = self.d.dedup("pipe1", "s1", "h1")
        self.assertTrue(rid.startswith("psdd-"))

    # --- get_stats ---

    def test_get_stats_empty(self):
        stats = self.d.get_stats()
        self.assertEqual(stats["total_records"], 0)
        self.assertEqual(stats["unique_pipelines"], 0)
        self.assertEqual(stats["unique_steps"], 0)

    def test_get_stats(self):
        self.d.dedup("pipe1", "s1", "h1")
        self.d.dedup("pipe2", "s1", "h2")
        self.d.dedup("pipe1", "s2", "h3")
        stats = self.d.get_stats()
        self.assertEqual(stats["total_records"], 3)
        self.assertEqual(stats["unique_pipelines"], 2)
        self.assertEqual(stats["unique_steps"], 2)

    # --- reset ---

    def test_reset_clears_entries(self):
        self.d.dedup("pipe1", "s1", "h1")
        self.d.dedup("pipe2", "s2", "h2")
        self.d.reset()
        self.assertEqual(self.d.get_dedup_count(), 0)

    def test_reset_clears_callbacks(self):
        self.d._callbacks["cb1"] = lambda e, d: None
        self.d.on_change = lambda e, d: None
        self.d.reset()
        self.assertIsNone(self.d.on_change)
        self.assertEqual(len(self.d._callbacks), 0)

    def test_reset_allows_new_entries(self):
        self.d.dedup("pipe1", "s1", "h1")
        self.d.reset()
        rid = self.d.dedup("pipe2", "s2", "h2")
        self.assertIsNotNone(self.d.get_dedup(rid))
        self.assertEqual(self.d.get_dedup_count(), 1)

    # --- pruning ---

    def test_prune_removes_oldest_quarter(self):
        original_max = PipelineStepDeduper.MAX_ENTRIES
        PipelineStepDeduper.MAX_ENTRIES = 20
        try:
            for i in range(25):
                self.d.dedup("pipe1", f"s{i}", f"h{i}")
            # After exceeding 20, oldest quarter (5) should be pruned
            self.assertLessEqual(self.d.get_dedup_count(), 20)
        finally:
            PipelineStepDeduper.MAX_ENTRIES = original_max

    # --- state dataclass ---

    def test_state_dataclass_defaults(self):
        state = PipelineStepDeduperState()
        self.assertEqual(state.entries, {})
        self.assertEqual(state._seq, 0)


if __name__ == "__main__":
    unittest.main()
