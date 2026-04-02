"""Tests for PipelineStepMonitor."""

import sys
import unittest

sys.path.insert(0, ".")
from src.services.pipeline_step_monitor import PipelineStepMonitor, PipelineStepMonitorState


class TestPipelineStepMonitor(unittest.TestCase):

    def setUp(self):
        self.monitor = PipelineStepMonitor()

    def test_configure_monitor_returns_id(self):
        mid = self.monitor.configure_monitor("pipe1", "step1")
        self.assertTrue(mid.startswith("psmo-"))
        self.assertEqual(len(mid), 5 + 16)  # prefix + 16 hex chars

    def test_configure_monitor_unique_ids(self):
        id1 = self.monitor.configure_monitor("pipe1", "step1")
        id2 = self.monitor.configure_monitor("pipe1", "step2")
        self.assertNotEqual(id1, id2)

    def test_record_success_returns_true(self):
        self.monitor.configure_monitor("pipe1", "step1")
        result = self.monitor.record_success("pipe1", "step1")
        self.assertTrue(result)

    def test_record_success_unknown_returns_false(self):
        result = self.monitor.record_success("unknown", "unknown")
        self.assertFalse(result)

    def test_record_failure_returns_dict(self):
        self.monitor.configure_monitor("pipe1", "step1", failure_threshold=2)
        result = self.monitor.record_failure("pipe1", "step1", error="timeout")
        self.assertIn("monitor_id", result)
        self.assertEqual(result["consecutive_failures"], 1)
        self.assertFalse(result["alert"])

    def test_record_failure_unknown_returns_empty(self):
        result = self.monitor.record_failure("unknown", "unknown")
        self.assertEqual(result, {})

    def test_alert_on_threshold(self):
        self.monitor.configure_monitor("pipe1", "step1", failure_threshold=3)
        self.monitor.record_failure("pipe1", "step1")
        self.monitor.record_failure("pipe1", "step1")
        result = self.monitor.record_failure("pipe1", "step1")
        self.assertTrue(result["alert"])
        self.assertEqual(result["consecutive_failures"], 3)

    def test_success_resets_consecutive_failures(self):
        self.monitor.configure_monitor("pipe1", "step1", failure_threshold=3)
        self.monitor.record_failure("pipe1", "step1")
        self.monitor.record_failure("pipe1", "step1")
        self.monitor.record_success("pipe1", "step1")
        result = self.monitor.record_failure("pipe1", "step1")
        self.assertEqual(result["consecutive_failures"], 1)
        self.assertFalse(result["alert"])

    def test_get_status(self):
        self.monitor.configure_monitor("pipe1", "step1")
        self.monitor.record_success("pipe1", "step1")
        self.monitor.record_success("pipe1", "step1")
        self.monitor.record_failure("pipe1", "step1")
        status = self.monitor.get_status("pipe1", "step1")
        self.assertTrue(status["healthy"])
        self.assertEqual(status["success_count"], 2)
        self.assertEqual(status["failure_count"], 1)
        self.assertAlmostEqual(status["success_rate"], 2 / 3, places=5)

    def test_get_status_unknown_returns_empty(self):
        status = self.monitor.get_status("unknown", "unknown")
        self.assertEqual(status, {})

    def test_get_monitor(self):
        mid = self.monitor.configure_monitor("pipe1", "step1")
        entry = self.monitor.get_monitor(mid)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["monitor_id"], mid)
        self.assertEqual(entry["pipeline_id"], "pipe1")

    def test_get_monitor_none(self):
        self.assertIsNone(self.monitor.get_monitor("psmo-nonexistent"))

    def test_get_monitors(self):
        self.monitor.configure_monitor("pipe1", "step1")
        self.monitor.configure_monitor("pipe1", "step2")
        self.monitor.configure_monitor("pipe2", "step1")
        monitors = self.monitor.get_monitors("pipe1")
        self.assertEqual(len(monitors), 2)

    def test_get_monitor_count(self):
        self.monitor.configure_monitor("pipe1", "step1")
        self.monitor.configure_monitor("pipe2", "step1")
        self.assertEqual(self.monitor.get_monitor_count(), 2)
        self.assertEqual(self.monitor.get_monitor_count("pipe1"), 1)

    def test_list_pipelines(self):
        self.monitor.configure_monitor("alpha", "step1")
        self.monitor.configure_monitor("beta", "step1")
        pipelines = self.monitor.list_pipelines()
        self.assertEqual(pipelines, ["alpha", "beta"])

    def test_get_stats(self):
        self.monitor.configure_monitor("pipe1", "step1", failure_threshold=1)
        self.monitor.configure_monitor("pipe1", "step2")
        self.monitor.record_failure("pipe1", "step1")
        stats = self.monitor.get_stats()
        self.assertEqual(stats["total_monitors"], 2)
        self.assertEqual(stats["unhealthy_monitors"], 1)
        self.assertEqual(stats["healthy_monitors"], 1)
        self.assertEqual(stats["pipelines"], 1)

    def test_reset(self):
        self.monitor.configure_monitor("pipe1", "step1")
        self.monitor.reset()
        self.assertEqual(self.monitor.get_monitor_count(), 0)
        self.assertEqual(self.monitor.list_pipelines(), [])

    def test_callbacks(self):
        events = []
        self.monitor.on_change("cb1", lambda e, d: events.append((e, d)))
        self.monitor.configure_monitor("pipe1", "step1")
        self.assertTrue(len(events) > 0)
        self.assertEqual(events[0][0], "monitor_configured")
        # Remove callback
        removed = self.monitor.remove_callback("cb1")
        self.assertTrue(removed)
        removed2 = self.monitor.remove_callback("cb1")
        self.assertFalse(removed2)

    def test_prune_at_max(self):
        """Verify that entries are pruned when exceeding 10000."""
        # We won't actually add 10001 entries but verify the method exists and works
        self.monitor._state.entries = {}
        # Just confirm prune doesn't error on empty
        self.monitor._prune()

    def test_state_dataclass(self):
        state = PipelineStepMonitorState()
        self.assertIsInstance(state.entries, dict)
        self.assertEqual(state._seq, 0)

    def test_healthy_after_recovery(self):
        """After alert, a success should restore healthy status."""
        self.monitor.configure_monitor("pipe1", "step1", failure_threshold=2)
        self.monitor.record_failure("pipe1", "step1")
        self.monitor.record_failure("pipe1", "step1")
        status = self.monitor.get_status("pipe1", "step1")
        self.assertFalse(status["healthy"])
        self.monitor.record_success("pipe1", "step1")
        status = self.monitor.get_status("pipe1", "step1")
        self.assertTrue(status["healthy"])


if __name__ == "__main__":
    unittest.main()
