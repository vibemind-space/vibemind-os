"""Tests for PipelineDataAccumulator."""

import sys
import time
import unittest

sys.path.insert(0, ".")
from src.services.pipeline_data_accumulator import PipelineDataAccumulator, PipelineDataAccumulatorState


class TestPipelineDataAccumulator(unittest.TestCase):

    def setUp(self):
        self.acc = PipelineDataAccumulator()

    def test_create_accumulator(self):
        acc_id = self.acc.create_accumulator("pipe-1")
        self.assertTrue(acc_id.startswith("pda2-"))
        self.assertEqual(len(acc_id), 5 + 16)  # "pda2-" + 16 hex chars

    def test_add_below_threshold_returns_empty(self):
        acc_id = self.acc.create_accumulator("pipe-1", flush_size=5)
        result = self.acc.add(acc_id, {"x": 1})
        self.assertEqual(result, [])

    def test_add_reaches_flush_size(self):
        acc_id = self.acc.create_accumulator("pipe-1", flush_size=3)
        self.acc.add(acc_id, "r1")
        self.acc.add(acc_id, "r2")
        flushed = self.acc.add(acc_id, "r3")
        self.assertEqual(flushed, ["r1", "r2", "r3"])
        # After flush, buffer should be empty
        self.assertEqual(self.acc.get_current(acc_id), [])

    def test_flush_force(self):
        acc_id = self.acc.create_accumulator("pipe-1", flush_size=100)
        self.acc.add(acc_id, "a")
        self.acc.add(acc_id, "b")
        flushed = self.acc.flush(acc_id)
        self.assertEqual(flushed, ["a", "b"])
        self.assertEqual(self.acc.get_current(acc_id), [])

    def test_get_current_peek(self):
        acc_id = self.acc.create_accumulator("pipe-1")
        self.acc.add(acc_id, 42)
        current = self.acc.get_current(acc_id)
        self.assertEqual(current, [42])
        # Should still be there (no flush)
        self.assertEqual(self.acc.get_current(acc_id), [42])

    def test_get_accumulator(self):
        acc_id = self.acc.create_accumulator("pipe-1", flush_size=50)
        info = self.acc.get_accumulator(acc_id)
        self.assertIsNotNone(info)
        self.assertEqual(info["pipeline_id"], "pipe-1")
        self.assertEqual(info["flush_size"], 50)
        self.assertIsNone(self.acc.get_accumulator("nonexistent"))

    def test_get_accumulators_by_pipeline(self):
        self.acc.create_accumulator("pipe-A")
        self.acc.create_accumulator("pipe-A")
        self.acc.create_accumulator("pipe-B")
        result = self.acc.get_accumulators("pipe-A")
        self.assertEqual(len(result), 2)
        self.assertTrue(all(r["pipeline_id"] == "pipe-A" for r in result))

    def test_get_accumulator_count(self):
        self.acc.create_accumulator("p1")
        self.acc.create_accumulator("p1")
        self.acc.create_accumulator("p2")
        self.assertEqual(self.acc.get_accumulator_count(), 3)
        self.assertEqual(self.acc.get_accumulator_count("p1"), 2)
        self.assertEqual(self.acc.get_accumulator_count("p2"), 1)
        self.assertEqual(self.acc.get_accumulator_count("p99"), 0)

    def test_list_pipelines(self):
        self.acc.create_accumulator("alpha")
        self.acc.create_accumulator("beta")
        self.acc.create_accumulator("alpha")
        pipelines = self.acc.list_pipelines()
        self.assertIn("alpha", pipelines)
        self.assertIn("beta", pipelines)
        self.assertEqual(len(pipelines), 2)

    def test_callbacks(self):
        events = []
        self.acc.on_change("tracker", lambda evt, data: events.append((evt, data)))
        acc_id = self.acc.create_accumulator("pipe-1", flush_size=2)
        self.acc.add(acc_id, "x")
        self.acc.add(acc_id, "y")  # triggers flush
        event_types = [e[0] for e in events]
        self.assertIn("created", event_types)
        self.assertIn("record_added", event_types)
        self.assertIn("flushed", event_types)
        # Remove callback
        self.assertTrue(self.acc.remove_callback("tracker"))
        self.assertFalse(self.acc.remove_callback("nonexistent"))

    def test_get_stats_and_reset(self):
        self.acc.create_accumulator("s1")
        acc_id = self.acc.create_accumulator("s2")
        self.acc.add(acc_id, "data")
        stats = self.acc.get_stats()
        self.assertEqual(stats["total_accumulators"], 2)
        self.assertEqual(stats["total_buffered_records"], 1)
        self.assertEqual(stats["pipelines"], 2)
        self.assertGreater(stats["seq"], 0)
        self.acc.reset()
        self.assertEqual(self.acc.get_accumulator_count(), 0)

    def test_add_nonexistent_raises(self):
        with self.assertRaises(KeyError):
            self.acc.add("bad-id", "record")

    def test_flush_nonexistent_raises(self):
        with self.assertRaises(KeyError):
            self.acc.flush("bad-id")

    def test_unique_ids(self):
        ids = set()
        for i in range(20):
            aid = self.acc.create_accumulator(f"pipe-{i % 3}")
            ids.add(aid)
        self.assertEqual(len(ids), 20)

    def test_flush_interval_trigger(self):
        acc_id = self.acc.create_accumulator("pipe-t", flush_size=9999, flush_interval_seconds=0.01)
        self.acc.add(acc_id, "first")
        time.sleep(0.02)
        flushed = self.acc.add(acc_id, "second")
        self.assertEqual(flushed, ["first", "second"])

    def test_state_dataclass(self):
        state = PipelineDataAccumulatorState()
        self.assertIsInstance(state.entries, dict)
        self.assertEqual(state._seq, 0)


if __name__ == "__main__":
    unittest.main()
