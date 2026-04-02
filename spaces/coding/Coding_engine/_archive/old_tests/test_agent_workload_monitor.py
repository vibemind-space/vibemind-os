"""Tests for AgentWorkloadMonitor."""

import sys
import unittest

sys.path.insert(0, ".")
from src.services.agent_workload_monitor import AgentWorkloadMonitor


class TestAgentWorkloadMonitor(unittest.TestCase):
    def setUp(self):
        self.monitor = AgentWorkloadMonitor()

    def test_register_agent(self):
        mid = self.monitor.register_agent("agent-1", max_concurrent=5)
        self.assertTrue(mid.startswith("awm-"))
        self.assertIn("agent-1", self.monitor.list_agents())

    def test_register_agent_default_max(self):
        mid = self.monitor.register_agent("agent-2")
        entry = self.monitor.get_monitor(mid)
        self.assertEqual(entry["max_concurrent"], 10)

    def test_record_task_start(self):
        self.monitor.register_agent("a1", max_concurrent=3)
        self.assertTrue(self.monitor.record_task_start("a1"))
        wl = self.monitor.get_workload("a1")
        self.assertEqual(wl["active_tasks"], 1)

    def test_record_task_start_unregistered(self):
        self.assertFalse(self.monitor.record_task_start("unknown"))

    def test_record_task_end(self):
        self.monitor.register_agent("a1", max_concurrent=3)
        self.monitor.record_task_start("a1")
        self.monitor.record_task_start("a1")
        self.assertTrue(self.monitor.record_task_end("a1"))
        wl = self.monitor.get_workload("a1")
        self.assertEqual(wl["active_tasks"], 1)

    def test_record_task_end_no_active(self):
        self.monitor.register_agent("a1")
        self.assertFalse(self.monitor.record_task_end("a1"))

    def test_record_task_end_unregistered(self):
        self.assertFalse(self.monitor.record_task_end("unknown"))

    def test_get_workload(self):
        self.monitor.register_agent("a1", max_concurrent=4)
        self.monitor.record_task_start("a1")
        self.monitor.record_task_start("a1")
        wl = self.monitor.get_workload("a1")
        self.assertEqual(wl["active_tasks"], 2)
        self.assertEqual(wl["max_concurrent"], 4)
        self.assertAlmostEqual(wl["utilization_percent"], 50.0)
        self.assertFalse(wl["is_overloaded"])

    def test_get_workload_overloaded(self):
        self.monitor.register_agent("a1", max_concurrent=2)
        self.monitor.record_task_start("a1")
        self.monitor.record_task_start("a1")
        wl = self.monitor.get_workload("a1")
        self.assertTrue(wl["is_overloaded"])

    def test_get_workload_unknown_agent(self):
        self.assertEqual(self.monitor.get_workload("nope"), {})

    def test_get_least_loaded(self):
        self.monitor.register_agent("a1", max_concurrent=10)
        self.monitor.register_agent("a2", max_concurrent=10)
        self.monitor.register_agent("a3", max_concurrent=10)
        self.monitor.record_task_start("a1")
        self.monitor.record_task_start("a1")
        self.monitor.record_task_start("a1")
        self.monitor.record_task_start("a2")
        # a3 has 0 active tasks
        result = self.monitor.get_least_loaded(limit=2)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["agent_id"], "a3")
        self.assertEqual(result[1]["agent_id"], "a2")

    def test_get_monitor_and_count(self):
        mid = self.monitor.register_agent("a1")
        self.assertIsNotNone(self.monitor.get_monitor(mid))
        self.assertEqual(self.monitor.get_monitor_count(), 1)
        self.assertIsNone(self.monitor.get_monitor("awm-nonexistent"))

    def test_list_agents(self):
        self.monitor.register_agent("x")
        self.monitor.register_agent("y")
        agents = self.monitor.list_agents()
        self.assertIn("x", agents)
        self.assertIn("y", agents)
        self.assertEqual(len(agents), 2)

    def test_get_stats(self):
        self.monitor.register_agent("a1", max_concurrent=10)
        self.monitor.record_task_start("a1")
        stats = self.monitor.get_stats()
        self.assertEqual(stats["total_agents"], 1)
        self.assertEqual(stats["total_active_tasks"], 1)
        self.assertEqual(stats["total_capacity"], 10)
        self.assertAlmostEqual(stats["overall_utilization_percent"], 10.0)

    def test_reset(self):
        self.monitor.register_agent("a1")
        self.monitor.on_change(lambda e, d: None)
        self.monitor.reset()
        self.assertEqual(self.monitor.get_monitor_count(), 0)
        self.assertEqual(self.monitor.list_agents(), [])
        stats = self.monitor.get_stats()
        self.assertEqual(stats["total_agents"], 0)
        self.assertEqual(stats["callbacks_registered"], 0)

    def test_callbacks(self):
        events = []
        cb_id = self.monitor.on_change(lambda e, d: events.append((e, d)))
        self.assertTrue(cb_id.startswith("awm-"))
        self.monitor.register_agent("a1")
        self.monitor.record_task_start("a1")
        self.monitor.record_task_end("a1")
        self.assertEqual(len(events), 3)
        self.assertEqual(events[0][0], "agent_registered")
        self.assertEqual(events[1][0], "task_started")
        self.assertEqual(events[2][0], "task_ended")
        self.assertTrue(self.monitor.remove_callback(cb_id))
        self.assertFalse(self.monitor.remove_callback("nonexistent"))

    def test_unique_ids(self):
        mid1 = self.monitor.register_agent("a1")
        mid2 = self.monitor.register_agent("a2")
        self.assertNotEqual(mid1, mid2)

    def test_prune_max_entries(self):
        for i in range(10050):
            self.monitor.register_agent(f"agent-{i}", max_concurrent=1)
        self.assertLessEqual(self.monitor.get_monitor_count(), 10000)


if __name__ == "__main__":
    unittest.main()
