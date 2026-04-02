"""Tests for AgentMetricDashboard."""

import sys
import unittest

sys.path.insert(0, ".")
from src.services.agent_metric_dashboard import AgentMetricDashboard


class TestAgentMetricDashboard(unittest.TestCase):
    def setUp(self):
        self.dashboard = AgentMetricDashboard()

    def test_register_metric_returns_id(self):
        mid = self.dashboard.register_metric("agent1", "cpu_usage")
        self.assertTrue(mid.startswith("amd-"))
        self.assertEqual(len(mid), 4 + 16)  # prefix + 16 hex chars

    def test_register_metric_invalid_type(self):
        with self.assertRaises(ValueError):
            self.dashboard.register_metric("agent1", "m", metric_type="invalid")

    def test_record_value_success(self):
        self.dashboard.register_metric("agent1", "cpu")
        result = self.dashboard.record_value("agent1", "cpu", 42)
        self.assertTrue(result)

    def test_record_value_unregistered(self):
        result = self.dashboard.record_value("agent1", "missing", 10)
        self.assertFalse(result)

    def test_get_metric_stats(self):
        self.dashboard.register_metric("agent1", "mem")
        self.dashboard.record_value("agent1", "mem", 10)
        self.dashboard.record_value("agent1", "mem", 20)
        self.dashboard.record_value("agent1", "mem", 30)

        m = self.dashboard.get_metric("agent1", "mem")
        self.assertEqual(m["current"], 30)
        self.assertEqual(m["min"], 10)
        self.assertEqual(m["max"], 30)
        self.assertEqual(m["avg"], 20.0)
        self.assertEqual(m["count"], 3)

    def test_get_metric_empty(self):
        result = self.dashboard.get_metric("nope", "nope")
        self.assertEqual(result, {})

    def test_get_dashboard(self):
        self.dashboard.register_metric("agent1", "cpu", "gauge")
        self.dashboard.register_metric("agent1", "mem", "counter")
        self.dashboard.record_value("agent1", "cpu", 50)
        self.dashboard.record_value("agent1", "mem", 100)

        db = self.dashboard.get_dashboard("agent1")
        self.assertIn("cpu", db)
        self.assertIn("mem", db)
        self.assertEqual(db["cpu"]["metric_type"], "gauge")
        self.assertEqual(db["mem"]["metric_type"], "counter")

    def test_get_all_dashboards(self):
        self.dashboard.register_metric("a1", "m1")
        self.dashboard.register_metric("a2", "m2")

        all_db = self.dashboard.get_all_dashboards()
        self.assertIn("a1", all_db)
        self.assertIn("a2", all_db)

    def test_get_metric_entry(self):
        mid = self.dashboard.register_metric("agent1", "lat")
        entry = self.dashboard.get_metric_entry(mid)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["agent_id"], "agent1")
        self.assertEqual(entry["metric_name"], "lat")

    def test_get_metric_entry_missing(self):
        self.assertIsNone(self.dashboard.get_metric_entry("amd-doesnotexist"))

    def test_get_metric_count(self):
        self.dashboard.register_metric("a1", "m1")
        self.dashboard.register_metric("a1", "m2")
        self.dashboard.register_metric("a2", "m3")

        self.assertEqual(self.dashboard.get_metric_count(), 3)
        self.assertEqual(self.dashboard.get_metric_count("a1"), 2)
        self.assertEqual(self.dashboard.get_metric_count("a2"), 1)

    def test_list_agents(self):
        self.dashboard.register_metric("b_agent", "m1")
        self.dashboard.register_metric("a_agent", "m2")
        agents = self.dashboard.list_agents()
        self.assertEqual(agents, ["a_agent", "b_agent"])

    def test_callbacks(self):
        events = []
        cb_id = self.dashboard.on_change(lambda e, d: events.append((e, d)))
        self.assertTrue(cb_id.startswith("amd-"))

        self.dashboard.register_metric("a1", "m1")
        self.assertTrue(len(events) > 0)
        self.assertEqual(events[-1][0], "metric_registered")

        removed = self.dashboard.remove_callback(cb_id)
        self.assertTrue(removed)
        removed2 = self.dashboard.remove_callback(cb_id)
        self.assertFalse(removed2)

    def test_get_stats(self):
        self.dashboard.register_metric("a1", "m1")
        stats = self.dashboard.get_stats()
        self.assertEqual(stats["total_metrics"], 1)
        self.assertEqual(stats["total_agents"], 1)

    def test_reset(self):
        self.dashboard.register_metric("a1", "m1")
        self.dashboard.on_change(lambda e, d: None)
        self.dashboard.reset()
        self.assertEqual(self.dashboard.get_metric_count(), 0)
        self.assertEqual(self.dashboard.get_stats()["callbacks"], 0)

    def test_prune_at_max(self):
        dash = AgentMetricDashboard()
        for i in range(10005):
            dash.register_metric(f"agent_{i}", f"metric_{i}")
        self.assertLessEqual(len(dash._state.entries), 10000)

    def test_histogram_type(self):
        mid = self.dashboard.register_metric("a1", "latency", "histogram")
        entry = self.dashboard.get_metric_entry(mid)
        self.assertEqual(entry["metric_type"], "histogram")


if __name__ == "__main__":
    unittest.main()
