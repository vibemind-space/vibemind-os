"""Tests for AgentHealthChecker."""

import sys
import unittest

sys.path.insert(0, ".")
from src.services.agent_health_checker import AgentHealthChecker


class TestAgentHealthChecker(unittest.TestCase):

    def setUp(self):
        self.checker = AgentHealthChecker()

    def test_register_check(self):
        cid = self.checker.register_check("agent-1", "cpu")
        self.assertTrue(cid.startswith("ahc-"))
        self.assertEqual(len(cid), 4 + 16)

    def test_run_check_no_fn(self):
        self.checker.register_check("agent-1", "cpu")
        result = self.checker.run_check("agent-1", "cpu")
        self.assertEqual(result["status"], "healthy")
        self.assertIn("timestamp", result)
        self.assertIsNotNone(result["check_id"])

    def test_run_check_with_fn_healthy(self):
        self.checker.register_check("agent-1", "mem", check_fn=lambda: True)
        result = self.checker.run_check("agent-1", "mem")
        self.assertEqual(result["status"], "healthy")

    def test_run_check_with_fn_unhealthy(self):
        self.checker.register_check("agent-1", "disk", check_fn=lambda: False)
        result = self.checker.run_check("agent-1", "disk")
        self.assertEqual(result["status"], "unhealthy")

    def test_run_check_with_fn_exception(self):
        def bad_fn():
            raise RuntimeError("boom")
        self.checker.register_check("agent-1", "net", check_fn=bad_fn)
        result = self.checker.run_check("agent-1", "net")
        self.assertEqual(result["status"], "unhealthy")
        self.assertIn("boom", result["message"])

    def test_run_check_not_found(self):
        result = self.checker.run_check("agent-1", "nonexistent")
        self.assertEqual(result["status"], "unhealthy")
        self.assertIsNone(result["check_id"])

    def test_run_all_checks(self):
        self.checker.register_check("agent-1", "cpu")
        self.checker.register_check("agent-1", "mem")
        results = self.checker.run_all_checks("agent-1")
        self.assertEqual(len(results), 2)

    def test_get_health_status_healthy(self):
        self.checker.register_check("agent-1", "cpu")
        status = self.checker.get_health_status("agent-1")
        self.assertEqual(status, "healthy")

    def test_get_health_status_unhealthy(self):
        self.checker.register_check("agent-1", "cpu", check_fn=lambda: False)
        status = self.checker.get_health_status("agent-1")
        self.assertEqual(status, "unhealthy")

    def test_get_check_history(self):
        self.checker.register_check("agent-1", "cpu")
        self.checker.run_check("agent-1", "cpu")
        self.checker.run_check("agent-1", "cpu")
        history = self.checker.get_check_history("agent-1", "cpu")
        self.assertEqual(len(history), 2)

    def test_get_check_history_limit(self):
        self.checker.register_check("agent-1", "cpu")
        for _ in range(20):
            self.checker.run_check("agent-1", "cpu")
        history = self.checker.get_check_history("agent-1", "cpu", limit=5)
        self.assertEqual(len(history), 5)

    def test_remove_check(self):
        cid = self.checker.register_check("agent-1", "cpu")
        self.assertTrue(self.checker.remove_check(cid))
        self.assertFalse(self.checker.remove_check(cid))
        self.assertEqual(self.checker.get_check_count(), 0)

    def test_get_checks(self):
        self.checker.register_check("agent-1", "cpu")
        self.checker.register_check("agent-1", "mem")
        checks = self.checker.get_checks("agent-1")
        self.assertEqual(len(checks), 2)
        names = {c["check_name"] for c in checks}
        self.assertEqual(names, {"cpu", "mem"})

    def test_get_check_count(self):
        self.checker.register_check("agent-1", "cpu")
        self.checker.register_check("agent-2", "mem")
        self.assertEqual(self.checker.get_check_count(), 2)
        self.assertEqual(self.checker.get_check_count("agent-1"), 1)

    def test_list_agents(self):
        self.checker.register_check("agent-1", "cpu")
        self.checker.register_check("agent-2", "mem")
        agents = self.checker.list_agents()
        self.assertEqual(agents, ["agent-1", "agent-2"])

    def test_get_stats(self):
        self.checker.register_check("agent-1", "cpu")
        stats = self.checker.get_stats()
        self.assertEqual(stats["total_checks"], 1)
        self.assertEqual(stats["agents"], 1)

    def test_callbacks(self):
        events = []
        self.checker.on_change("test", lambda action, detail: events.append((action, detail)))
        self.checker.register_check("agent-1", "cpu")
        self.assertGreater(len(events), 0)
        self.assertEqual(events[0][0], "register_check")
        self.assertTrue(self.checker.remove_callback("test"))
        self.assertFalse(self.checker.remove_callback("test"))

    def test_reset(self):
        self.checker.register_check("agent-1", "cpu")
        self.checker.reset()
        self.assertEqual(self.checker.get_check_count(), 0)
        self.assertEqual(self.checker.list_agents(), [])

    def test_check_fn_returns_dict(self):
        self.checker.register_check("agent-1", "custom", check_fn=lambda: {"status": "unhealthy", "message": "low disk"})
        result = self.checker.run_check("agent-1", "custom")
        self.assertEqual(result["status"], "unhealthy")
        self.assertEqual(result["message"], "low disk")

    def test_unique_ids(self):
        id1 = self.checker.register_check("agent-1", "cpu")
        id2 = self.checker.register_check("agent-1", "cpu")
        self.assertNotEqual(id1, id2)

    def test_health_status_no_checks(self):
        status = self.checker.get_health_status("nonexistent")
        self.assertEqual(status, "healthy")


if __name__ == "__main__":
    unittest.main()
