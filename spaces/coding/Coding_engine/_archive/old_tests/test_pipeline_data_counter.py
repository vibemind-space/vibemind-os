"""Tests for PipelineDataCounter."""

import sys
import unittest

sys.path.insert(0, ".")
from src.services.pipeline_data_counter import PipelineDataCounter, PipelineDataCounterState


class TestPipelineDataCounter(unittest.TestCase):

    def setUp(self):
        self.counter = PipelineDataCounter()

    def test_create_counter(self):
        cid = self.counter.create_counter("pipe-1", "status")
        self.assertTrue(cid.startswith("pdct-"))
        self.assertIsNotNone(self.counter.get_counter(cid))

    def test_create_counter_fields(self):
        cid = self.counter.create_counter("pipe-1", "color")
        entry = self.counter.get_counter(cid)
        self.assertEqual(entry["pipeline_id"], "pipe-1")
        self.assertEqual(entry["field"], "color")
        self.assertEqual(entry["counts"], {})

    def test_increment_and_get_count(self):
        cid = self.counter.create_counter("pipe-1", "status")
        result = self.counter.increment(cid, "active", 3)
        self.assertEqual(result, 3)
        self.assertEqual(self.counter.get_count(cid, "active"), 3)
        self.counter.increment(cid, "active", 2)
        self.assertEqual(self.counter.get_count(cid, "active"), 5)

    def test_increment_missing_counter_raises(self):
        with self.assertRaises(KeyError):
            self.counter.increment("pdct-nonexistent", "x")

    def test_get_count_missing(self):
        self.assertEqual(self.counter.get_count("pdct-nope", "x"), 0)

    def test_count_records(self):
        self.counter.create_counter("pipe-2", "color")
        records = [
            {"color": "red"},
            {"color": "blue"},
            {"color": "red"},
            {"color": "green"},
        ]
        result = self.counter.count("pipe-2", records)
        self.assertEqual(result["red"], 2)
        self.assertEqual(result["blue"], 1)
        self.assertEqual(result["green"], 1)

    def test_get_top(self):
        cid = self.counter.create_counter("pipe-3", "x")
        self.counter.increment(cid, "a", 10)
        self.counter.increment(cid, "b", 5)
        self.counter.increment(cid, "c", 20)
        top = self.counter.get_top(cid, limit=2)
        self.assertEqual(len(top), 2)
        self.assertEqual(top[0], ("c", 20))
        self.assertEqual(top[1], ("a", 10))

    def test_get_top_missing_counter(self):
        self.assertEqual(self.counter.get_top("pdct-nope"), [])

    def test_get_counters_and_count(self):
        self.counter.create_counter("pipe-a", "f1")
        self.counter.create_counter("pipe-a", "f2")
        self.counter.create_counter("pipe-b", "f1")
        self.assertEqual(self.counter.get_counter_count("pipe-a"), 2)
        self.assertEqual(self.counter.get_counter_count("pipe-b"), 1)
        self.assertEqual(self.counter.get_counter_count(), 3)

    def test_list_pipelines(self):
        self.counter.create_counter("alpha", "x")
        self.counter.create_counter("beta", "y")
        self.counter.create_counter("alpha", "z")
        pipelines = self.counter.list_pipelines()
        self.assertIn("alpha", pipelines)
        self.assertIn("beta", pipelines)
        self.assertEqual(len(pipelines), 2)

    def test_callbacks(self):
        events = []
        cb_id = self.counter.on_change(lambda e, d: events.append((e, d)))
        self.counter.create_counter("p", "f")
        self.assertTrue(len(events) > 0)
        self.assertEqual(events[0][0], "counter_created")
        removed = self.counter.remove_callback(cb_id)
        self.assertTrue(removed)
        self.assertFalse(self.counter.remove_callback(cb_id))

    def test_get_stats(self):
        self.counter.create_counter("p1", "f1")
        cid = self.counter.create_counter("p2", "f2")
        self.counter.increment(cid, "val1")
        stats = self.counter.get_stats()
        self.assertEqual(stats["total_counters"], 2)
        self.assertEqual(stats["total_values"], 1)
        self.assertEqual(stats["pipelines"], 2)
        self.assertIn("uptime", stats)

    def test_reset(self):
        self.counter.create_counter("p", "f")
        self.counter.on_change(lambda e, d: None)
        self.counter.reset()
        self.assertEqual(self.counter.get_counter_count(), 0)
        self.assertEqual(len(self.counter._callbacks), 0)

    def test_prune_max_entries(self):
        original_max = PipelineDataCounter.MAX_ENTRIES
        PipelineDataCounter.MAX_ENTRIES = 5
        try:
            for i in range(8):
                self.counter.create_counter(f"p-{i}", f"f-{i}")
            self.assertLessEqual(self.counter.get_counter_count(), 5)
        finally:
            PipelineDataCounter.MAX_ENTRIES = original_max

    def test_state_dataclass(self):
        state = PipelineDataCounterState()
        self.assertEqual(state.entries, {})
        self.assertEqual(state._seq, 0)

    def test_unique_ids(self):
        id1 = self.counter.create_counter("p", "f")
        id2 = self.counter.create_counter("p", "f")
        self.assertNotEqual(id1, id2)


if __name__ == "__main__":
    unittest.main()
