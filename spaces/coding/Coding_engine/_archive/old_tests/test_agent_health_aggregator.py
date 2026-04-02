"""Tests for AgentHealthAggregator."""

import sys
import unittest

sys.path.insert(0, ".")

from src.services.agent_health_aggregator import AgentHealthAggregator


class TestAgentHealthAggregator(unittest.TestCase):

    def setUp(self):
        self.agg = AgentHealthAggregator()

    def test_report_health_returns_id_with_prefix(self):
        rid = self.agg.report_health("agent-1", "cpu")
        self.assertTrue(rid.startswith("aha-"))

    def test_report_health_default_status_healthy(self):
        rid = self.agg.report_health("agent-1", "cpu")
        report = self.agg.get_report(rid)
        self.assertEqual(report["status"], "healthy")

    def test_report_health_invalid_status_raises(self):
        with self.assertRaises(ValueError):
            self.agg.report_health("agent-1", "cpu", status="broken")

    def test_get_report_nonexistent_returns_none(self):
        self.assertIsNone(self.agg.get_report("aha-doesnotexist"))

    def test_get_agent_health_single_component(self):
        self.agg.report_health("agent-1", "cpu", "degraded")
        health = self.agg.get_agent_health("agent-1")
        self.assertEqual(health["overall"], "degraded")
        self.assertEqual(health["components"]["cpu"], "degraded")

    def test_get_agent_health_worst_status_wins(self):
        self.agg.report_health("agent-1", "cpu", "healthy")
        self.agg.report_health("agent-1", "memory", "unhealthy")
        health = self.agg.get_agent_health("agent-1")
        self.assertEqual(health["overall"], "unhealthy")

    def test_get_agent_health_unknown_agent(self):
        health = self.agg.get_agent_health("nonexistent")
        self.assertEqual(health["overall"], "healthy")
        self.assertEqual(health["components"], {})

    def test_get_system_health(self):
        self.agg.report_health("agent-1", "cpu", "healthy")
        self.agg.report_health("agent-2", "cpu", "degraded")
        self.agg.report_health("agent-3", "cpu", "unhealthy")
        sh = self.agg.get_system_health()
        self.assertEqual(sh["overall"], "unhealthy")
        self.assertEqual(sh["healthy_count"], 1)
        self.assertEqual(sh["degraded_count"], 1)
        self.assertEqual(sh["unhealthy_count"], 1)
        self.assertIn("agent-1", sh["agents"])

    def test_get_unhealthy_agents(self):
        self.agg.report_health("agent-1", "cpu", "healthy")
        self.agg.report_health("agent-2", "cpu", "unhealthy")
        self.agg.report_health("agent-3", "cpu", "degraded")
        unhealthy = self.agg.get_unhealthy_agents()
        self.assertEqual(unhealthy, ["agent-2"])

    def test_list_agents(self):
        self.agg.report_health("beta", "cpu")
        self.agg.report_health("alpha", "cpu")
        agents = self.agg.list_agents()
        self.assertEqual(agents, ["alpha", "beta"])

    def test_get_report_count(self):
        self.agg.report_health("a1", "cpu")
        self.agg.report_health("a1", "mem")
        self.agg.report_health("a2", "cpu")
        self.assertEqual(self.agg.get_report_count(), 3)
        self.assertEqual(self.agg.get_report_count("a1"), 2)
        self.assertEqual(self.agg.get_report_count("a2"), 1)

    def test_callbacks(self):
        events = []
        self.agg.on_change("cb1", lambda evt, data: events.append((evt, data)))
        self.agg.report_health("a1", "cpu")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "health_reported")

        self.assertTrue(self.agg.remove_callback("cb1"))
        self.assertFalse(self.agg.remove_callback("cb1"))
        self.agg.report_health("a1", "mem")
        self.assertEqual(len(events), 1)  # no new event

    def test_get_stats(self):
        self.agg.report_health("a1", "cpu")
        stats = self.agg.get_stats()
        self.assertEqual(stats["total_reports"], 1)
        self.assertEqual(stats["agent_count"], 1)
        self.assertGreaterEqual(stats["seq"], 1)

    def test_reset(self):
        self.agg.report_health("a1", "cpu")
        self.agg.on_change("cb1", lambda e, d: None)
        self.agg.reset()
        self.assertEqual(self.agg.get_report_count(), 0)
        self.assertEqual(self.agg.list_agents(), [])
        self.assertEqual(self.agg.get_stats()["callback_count"], 0)

    def test_prune_entries_at_max(self):
        for i in range(10050):
            self.agg.report_health(f"agent-{i % 100}", f"comp-{i}", "healthy")
        self.assertLessEqual(self.agg.get_report_count(), 10000)

    def test_unique_ids(self):
        id1 = self.agg.report_health("a1", "cpu", "healthy")
        id2 = self.agg.report_health("a1", "cpu", "healthy")
        self.assertNotEqual(id1, id2)

    def test_latest_component_status_wins(self):
        self.agg.report_health("a1", "cpu", "unhealthy")
        self.agg.report_health("a1", "cpu", "healthy")
        health = self.agg.get_agent_health("a1")
        self.assertEqual(health["components"]["cpu"], "healthy")
        self.assertEqual(health["overall"], "healthy")

    def test_report_with_details(self):
        rid = self.agg.report_health("a1", "cpu", details={"load": 0.95})
        report = self.agg.get_report(rid)
        self.assertEqual(report["details"], {"load": 0.95})


if __name__ == "__main__":
    unittest.main()
