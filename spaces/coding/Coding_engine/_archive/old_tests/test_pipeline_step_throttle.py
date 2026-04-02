"""Tests for PipelineStepThrottle."""

import sys
import time
import unittest

sys.path.insert(0, ".")
from src.services.pipeline_step_throttle import PipelineStepThrottle, PipelineStepThrottleState


class TestPipelineStepThrottle(unittest.TestCase):

    def setUp(self):
        self.throttle = PipelineStepThrottle()

    def test_set_throttle_returns_id(self):
        tid = self.throttle.set_throttle("pipe1", "step1", 5.0)
        self.assertTrue(tid.startswith("psth-"))
        self.assertEqual(len(tid), 5 + 16)  # prefix "psth-" + 16 hex chars

    def test_get_throttle(self):
        tid = self.throttle.set_throttle("pipe1", "step1", 10.0)
        info = self.throttle.get_throttle(tid)
        self.assertIsNotNone(info)
        self.assertEqual(info["pipeline_id"], "pipe1")
        self.assertEqual(info["step_name"], "step1")
        self.assertEqual(info["max_per_second"], 10.0)

    def test_get_throttle_not_found(self):
        result = self.throttle.get_throttle("psth-nonexistent")
        self.assertIsNone(result)

    def test_remove_throttle(self):
        tid = self.throttle.set_throttle("pipe1", "step1")
        self.assertTrue(self.throttle.remove_throttle(tid))
        self.assertIsNone(self.throttle.get_throttle(tid))
        self.assertFalse(self.throttle.remove_throttle(tid))

    def test_can_execute_no_throttle(self):
        self.assertTrue(self.throttle.can_execute("pipe1", "step1"))

    def test_can_execute_within_limit(self):
        self.throttle.set_throttle("pipe1", "step1", 100.0)
        self.assertTrue(self.throttle.can_execute("pipe1", "step1"))

    def test_record_execution_allowed(self):
        self.throttle.set_throttle("pipe1", "step1", 100.0)
        result = self.throttle.record_execution("pipe1", "step1")
        self.assertTrue(result)

    def test_record_execution_no_throttle(self):
        result = self.throttle.record_execution("pipe1", "step1")
        self.assertTrue(result)

    def test_record_execution_throttled(self):
        self.throttle.set_throttle("pipe1", "step1", 2.0)
        self.assertTrue(self.throttle.record_execution("pipe1", "step1"))
        self.assertTrue(self.throttle.record_execution("pipe1", "step1"))
        result = self.throttle.record_execution("pipe1", "step1")
        self.assertFalse(result)

    def test_get_throttle_info(self):
        self.throttle.set_throttle("pipe1", "step1", 10.0)
        self.throttle.record_execution("pipe1", "step1")
        info = self.throttle.get_throttle_info("pipe1", "step1")
        self.assertEqual(info["max_per_second"], 10.0)
        self.assertGreaterEqual(info["current_rate"], 1.0)
        self.assertEqual(info["throttled_count"], 0)

    def test_get_throttle_info_not_found(self):
        info = self.throttle.get_throttle_info("nope", "nope")
        self.assertEqual(info["max_per_second"], 0.0)

    def test_get_throttle_count(self):
        self.assertEqual(self.throttle.get_throttle_count(), 0)
        self.throttle.set_throttle("pipe1", "step1")
        self.throttle.set_throttle("pipe1", "step2")
        self.throttle.set_throttle("pipe2", "step1")
        self.assertEqual(self.throttle.get_throttle_count(), 3)
        self.assertEqual(self.throttle.get_throttle_count("pipe1"), 2)
        self.assertEqual(self.throttle.get_throttle_count("pipe2"), 1)

    def test_list_pipelines(self):
        self.throttle.set_throttle("beta", "s1")
        self.throttle.set_throttle("alpha", "s1")
        self.throttle.set_throttle("beta", "s2")
        result = self.throttle.list_pipelines()
        self.assertEqual(result, ["alpha", "beta"])

    def test_get_stats(self):
        self.throttle.set_throttle("p1", "s1", 1.0)
        self.throttle.record_execution("p1", "s1")
        self.throttle.record_execution("p1", "s1")  # throttled
        stats = self.throttle.get_stats()
        self.assertEqual(stats["total_throttles"], 1)
        self.assertEqual(stats["pipelines"], 1)
        self.assertGreaterEqual(stats["total_throttled_count"], 1)

    def test_reset(self):
        self.throttle.set_throttle("p1", "s1")
        self.throttle.reset()
        self.assertEqual(self.throttle.get_throttle_count(), 0)
        self.assertEqual(self.throttle.list_pipelines(), [])

    def test_on_change_and_remove_callback(self):
        events = []
        cb_id = self.throttle.on_change(lambda evt, data: events.append(evt))
        self.assertTrue(cb_id.startswith("psth-"))
        self.throttle.set_throttle("p1", "s1")
        self.assertIn("throttle_set", events)
        self.assertTrue(self.throttle.remove_callback(cb_id))
        self.assertFalse(self.throttle.remove_callback(cb_id))

    def test_unique_ids(self):
        ids = set()
        for i in range(50):
            tid = self.throttle.set_throttle(f"p{i}", "s1")
            ids.add(tid)
        self.assertEqual(len(ids), 50)

    def test_state_dataclass(self):
        state = PipelineStepThrottleState()
        self.assertEqual(state.entries, {})
        self.assertEqual(state._seq, 0)

    def test_prune_max_entries(self):
        throttle = PipelineStepThrottle()
        throttle.MAX_ENTRIES = 5
        for i in range(8):
            throttle.set_throttle(f"p{i}", "s1")
        self.assertLessEqual(len(throttle._state.entries), 5)


if __name__ == "__main__":
    unittest.main()
