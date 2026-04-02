"""Tests for PipelineStepTimeout."""

import sys
import time
import unittest

sys.path.insert(0, ".")
from src.services.pipeline_step_timeout import PipelineStepTimeout, PipelineStepTimeoutState


class TestPipelineStepTimeout(unittest.TestCase):
    def setUp(self):
        self.svc = PipelineStepTimeout()

    def test_set_timeout_returns_id(self):
        tid = self.svc.set_timeout("p1", "step_a", 30.0)
        self.assertTrue(tid.startswith("pst-"))
        self.assertEqual(len(tid), 4 + 16)

    def test_get_timeout(self):
        tid = self.svc.set_timeout("p1", "step_a", 60.0)
        entry = self.svc.get_timeout(tid)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["pipeline_id"], "p1")
        self.assertEqual(entry["step_name"], "step_a")
        self.assertEqual(entry["timeout_seconds"], 60.0)

    def test_get_timeout_not_found(self):
        self.assertIsNone(self.svc.get_timeout("pst-nonexistent00000"))

    def test_get_timeouts_by_pipeline(self):
        self.svc.set_timeout("p1", "s1", 10)
        self.svc.set_timeout("p1", "s2", 20)
        self.svc.set_timeout("p2", "s1", 30)
        result = self.svc.get_timeouts("p1")
        self.assertEqual(len(result), 2)

    def test_start_timer(self):
        self.svc.set_timeout("p1", "s1", 100)
        ok = self.svc.start_timer("p1", "s1")
        self.assertTrue(ok)

    def test_check_timeout_not_timed_out(self):
        self.svc.set_timeout("p1", "s1", 100)
        self.svc.start_timer("p1", "s1")
        result = self.svc.check_timeout("p1", "s1")
        self.assertFalse(result["timed_out"])
        self.assertGreater(result["remaining"], 0)

    def test_check_timeout_timed_out(self):
        self.svc.set_timeout("p1", "s1", 0.01)
        self.svc.start_timer("p1", "s1")
        time.sleep(0.02)
        result = self.svc.check_timeout("p1", "s1")
        self.assertTrue(result["timed_out"])
        self.assertEqual(result["remaining"], 0.0)

    def test_stop_timer(self):
        self.svc.set_timeout("p1", "s1", 100)
        self.svc.start_timer("p1", "s1")
        result = self.svc.stop_timer("p1", "s1")
        self.assertIn("elapsed", result)
        self.assertFalse(result["timed_out"])

    def test_get_timeout_count(self):
        self.svc.set_timeout("p1", "s1", 10)
        self.svc.set_timeout("p2", "s1", 20)
        self.assertEqual(self.svc.get_timeout_count(), 2)
        self.assertEqual(self.svc.get_timeout_count("p1"), 1)

    def test_list_pipelines(self):
        self.svc.set_timeout("p1", "s1", 10)
        self.svc.set_timeout("p2", "s1", 20)
        pipelines = self.svc.list_pipelines()
        self.assertIn("p1", pipelines)
        self.assertIn("p2", pipelines)

    def test_callbacks(self):
        events = []
        self.svc.on_change("test_cb", lambda action, detail: events.append(action))
        self.svc.set_timeout("p1", "s1", 10)
        self.assertIn("set_timeout", events)
        self.assertTrue(self.svc.remove_callback("test_cb"))
        self.assertFalse(self.svc.remove_callback("nonexistent"))

    def test_get_stats(self):
        self.svc.set_timeout("p1", "s1", 10)
        self.svc.start_timer("p1", "s1")
        stats = self.svc.get_stats()
        self.assertEqual(stats["total_entries"], 1)
        self.assertEqual(stats["active_timers"], 1)

    def test_reset(self):
        self.svc.set_timeout("p1", "s1", 10)
        self.svc.start_timer("p1", "s1")
        self.svc.reset()
        self.assertEqual(self.svc.get_timeout_count(), 0)
        stats = self.svc.get_stats()
        self.assertEqual(stats["active_timers"], 0)

    def test_unique_ids(self):
        id1 = self.svc.set_timeout("p1", "s1", 10)
        id2 = self.svc.set_timeout("p1", "s1", 10)
        self.assertNotEqual(id1, id2)

    def test_state_dataclass(self):
        state = PipelineStepTimeoutState()
        self.assertEqual(state.entries, {})
        self.assertEqual(state._seq, 0)

    def test_check_timeout_no_timer(self):
        result = self.svc.check_timeout("p1", "s1")
        self.assertFalse(result["timed_out"])
        self.assertEqual(result["elapsed"], 0.0)

    def test_stop_timer_no_timer(self):
        result = self.svc.stop_timer("p1", "s1")
        self.assertEqual(result["elapsed"], 0.0)
        self.assertFalse(result["timed_out"])


if __name__ == "__main__":
    unittest.main()
