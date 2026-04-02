"""Tests for AgentOperationLog."""

import sys
import time
import unittest

sys.path.insert(0, ".")

from src.services.agent_operation_log import AgentOperationLog


class TestAgentOperationLog(unittest.TestCase):
    """Tests for AgentOperationLog."""

    def setUp(self):
        self.log = AgentOperationLog()

    def test_start_and_get_operation(self):
        op_id = self.log.start_operation("agent-1", "build")
        self.assertTrue(op_id.startswith("aol-"))
        entry = self.log.get_operation(op_id)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["agent_id"], "agent-1")
        self.assertEqual(entry["operation"], "build")
        self.assertEqual(entry["status"], "running")
        self.assertIsNone(entry["end_time"])

    def test_end_operation(self):
        op_id = self.log.start_operation("agent-1", "deploy")
        result = self.log.end_operation(op_id, status="success", result={"ok": True})
        self.assertEqual(result["operation_id"], op_id)
        self.assertEqual(result["status"], "success")
        self.assertGreaterEqual(result["duration_ms"], 0.0)

        entry = self.log.get_operation(op_id)
        self.assertEqual(entry["status"], "success")
        self.assertIsNotNone(entry["end_time"])
        self.assertEqual(entry["result"], {"ok": True})

    def test_end_operation_missing(self):
        result = self.log.end_operation("aol-nonexistent")
        self.assertEqual(result["operation_id"], "aol-nonexistent")
        self.assertEqual(result["duration_ms"], 0.0)

    def test_get_operation_none(self):
        self.assertIsNone(self.log.get_operation("aol-nope"))

    def test_get_operations_filter(self):
        self.log.start_operation("agent-1", "build")
        self.log.start_operation("agent-1", "test")
        op3 = self.log.start_operation("agent-1", "build")
        self.log.end_operation(op3, status="failed")

        all_ops = self.log.get_operations("agent-1")
        self.assertEqual(len(all_ops), 3)

        build_ops = self.log.get_operations("agent-1", operation="build")
        self.assertEqual(len(build_ops), 2)

        failed_ops = self.log.get_operations("agent-1", status="failed")
        self.assertEqual(len(failed_ops), 1)

        build_failed = self.log.get_operations("agent-1", operation="build", status="failed")
        self.assertEqual(len(build_failed), 1)

    def test_get_latest_operation(self):
        self.log.start_operation("agent-1", "build")
        self.log.start_operation("agent-1", "test")
        op3 = self.log.start_operation("agent-1", "deploy")

        latest = self.log.get_latest_operation("agent-1")
        self.assertIsNotNone(latest)
        self.assertEqual(latest["operation_id"], op3)
        self.assertEqual(latest["operation"], "deploy")

    def test_get_latest_operation_none(self):
        self.assertIsNone(self.log.get_latest_operation("agent-404"))

    def test_get_average_duration(self):
        op1 = self.log.start_operation("agent-1", "build")
        op2 = self.log.start_operation("agent-1", "build")
        self.log.end_operation(op1)
        self.log.end_operation(op2)

        avg = self.log.get_average_duration("agent-1", "build")
        self.assertGreaterEqual(avg, 0.0)

    def test_get_average_duration_no_data(self):
        avg = self.log.get_average_duration("agent-1", "build")
        self.assertEqual(avg, 0.0)

    def test_get_operation_count(self):
        self.log.start_operation("agent-1", "build")
        self.log.start_operation("agent-2", "test")
        self.log.start_operation("agent-1", "deploy")

        self.assertEqual(self.log.get_operation_count(), 3)
        self.assertEqual(self.log.get_operation_count("agent-1"), 2)
        self.assertEqual(self.log.get_operation_count("agent-2"), 1)
        self.assertEqual(self.log.get_operation_count("agent-3"), 0)

    def test_list_agents(self):
        self.log.start_operation("agent-a", "build")
        self.log.start_operation("agent-b", "test")
        self.log.start_operation("agent-a", "deploy")

        agents = self.log.list_agents()
        self.assertEqual(sorted(agents), ["agent-a", "agent-b"])

    def test_callbacks(self):
        events = []

        def on_event(action, detail):
            events.append((action, detail))

        self.log.on_change("test_cb", on_event)
        op_id = self.log.start_operation("agent-1", "build")
        self.log.end_operation(op_id)

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0][0], "operation_started")
        self.assertEqual(events[1][0], "operation_ended")

        self.assertTrue(self.log.remove_callback("test_cb"))
        self.assertFalse(self.log.remove_callback("test_cb"))

    def test_pruning(self):
        log = AgentOperationLog(max_entries=10)
        for i in range(12):
            log.start_operation(f"agent-{i}", "build")

        self.assertLessEqual(log.get_operation_count(), 12)
        stats = log.get_stats()
        self.assertGreater(stats["total_pruned"], 0)

    def test_reset(self):
        self.log.start_operation("agent-1", "build")
        self.log.on_change("cb1", lambda a, d: None)
        self.log.reset()

        self.assertEqual(self.log.get_operation_count(), 0)
        self.assertEqual(self.log.list_agents(), [])
        stats = self.log.get_stats()
        self.assertEqual(stats["total_started"], 0)

    def test_metadata(self):
        op_id = self.log.start_operation("agent-1", "build", metadata={"branch": "main"})
        entry = self.log.get_operation(op_id)
        self.assertEqual(entry["metadata"], {"branch": "main"})

    def test_stats(self):
        op_id = self.log.start_operation("agent-1", "build")
        self.log.end_operation(op_id)
        self.log.get_operations("agent-1")

        stats = self.log.get_stats()
        self.assertEqual(stats["total_started"], 1)
        self.assertEqual(stats["total_ended"], 1)
        self.assertGreaterEqual(stats["total_queries"], 1)
        self.assertEqual(stats["current_entries"], 1)
        self.assertEqual(stats["max_entries"], 10000)


if __name__ == "__main__":
    unittest.main()
