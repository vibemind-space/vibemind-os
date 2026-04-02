"""Tests for AgentRateController service."""

import sys
import time
import unittest

sys.path.insert(0, ".")
from src.services.agent_rate_controller import AgentRateController


class TestAgentRateController(unittest.TestCase):

    def setUp(self):
        self.ctrl = AgentRateController()

    def test_set_limit(self):
        limit_id = self.ctrl.set_limit("agent-1", "deploy", 5, 60.0)
        self.assertTrue(limit_id.startswith("arco-"))
        self.assertEqual(len(limit_id), 5 + 16)  # "arco-" + 16 hex chars

    def test_get_limit(self):
        limit_id = self.ctrl.set_limit("agent-1", "deploy", 5, 60.0)
        info = self.ctrl.get_limit(limit_id)
        self.assertIsNotNone(info)
        self.assertEqual(info["agent_id"], "agent-1")
        self.assertEqual(info["operation"], "deploy")
        self.assertEqual(info["max_requests"], 5)
        self.assertEqual(info["window_seconds"], 60.0)

    def test_get_limit_not_found(self):
        self.assertIsNone(self.ctrl.get_limit("arco-nonexistent1234"))

    def test_check_rate_no_limit(self):
        result = self.ctrl.check_rate("agent-1", "deploy")
        self.assertTrue(result["allowed"])
        self.assertEqual(result["remaining"], -1)

    def test_check_rate_with_limit(self):
        self.ctrl.set_limit("agent-1", "deploy", 3, 60.0)
        result = self.ctrl.check_rate("agent-1", "deploy")
        self.assertTrue(result["allowed"])
        self.assertEqual(result["remaining"], 3)

    def test_record_request_allowed(self):
        self.ctrl.set_limit("agent-1", "deploy", 3, 60.0)
        self.assertTrue(self.ctrl.record_request("agent-1", "deploy"))
        self.assertTrue(self.ctrl.record_request("agent-1", "deploy"))
        self.assertTrue(self.ctrl.record_request("agent-1", "deploy"))

    def test_record_request_rate_exceeded(self):
        self.ctrl.set_limit("agent-1", "deploy", 2, 60.0)
        self.assertTrue(self.ctrl.record_request("agent-1", "deploy"))
        self.assertTrue(self.ctrl.record_request("agent-1", "deploy"))
        self.assertFalse(self.ctrl.record_request("agent-1", "deploy"))

    def test_get_usage(self):
        self.ctrl.set_limit("agent-1", "deploy", 5, 60.0)
        self.ctrl.record_request("agent-1", "deploy")
        self.ctrl.record_request("agent-1", "deploy")
        usage = self.ctrl.get_usage("agent-1", "deploy")
        self.assertEqual(usage["count"], 2)
        self.assertEqual(usage["limit"], 5)
        self.assertEqual(usage["remaining"], 3)
        self.assertEqual(usage["window_seconds"], 60.0)

    def test_get_usage_no_limit(self):
        usage = self.ctrl.get_usage("agent-1", "deploy")
        self.assertEqual(usage["count"], 0)
        self.assertEqual(usage["limit"], 0)

    def test_callbacks(self):
        events = []
        self.ctrl.on_change("test_cb", lambda action, detail: events.append((action, detail)))
        self.ctrl.set_limit("agent-1", "deploy", 5)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "set_limit")
        self.assertIn("limit_id", events[0][1])

    def test_remove_callback(self):
        self.ctrl.on_change("cb1", lambda a, d: None)
        self.assertTrue(self.ctrl.remove_callback("cb1"))
        self.assertFalse(self.ctrl.remove_callback("cb1"))

    def test_remove_limit(self):
        limit_id = self.ctrl.set_limit("agent-1", "deploy", 5)
        self.assertTrue(self.ctrl.remove_limit(limit_id))
        self.assertFalse(self.ctrl.remove_limit(limit_id))
        self.assertIsNone(self.ctrl.get_limit(limit_id))

    def test_get_limits(self):
        self.ctrl.set_limit("agent-1", "deploy", 5)
        self.ctrl.set_limit("agent-1", "build", 10)
        self.ctrl.set_limit("agent-2", "deploy", 3)
        limits = self.ctrl.get_limits("agent-1")
        self.assertEqual(len(limits), 2)

    def test_get_limit_count(self):
        self.ctrl.set_limit("agent-1", "deploy", 5)
        self.ctrl.set_limit("agent-1", "build", 10)
        self.ctrl.set_limit("agent-2", "deploy", 3)
        self.assertEqual(self.ctrl.get_limit_count(), 3)
        self.assertEqual(self.ctrl.get_limit_count("agent-1"), 2)
        self.assertEqual(self.ctrl.get_limit_count("agent-2"), 1)

    def test_list_agents(self):
        self.ctrl.set_limit("agent-1", "deploy", 5)
        self.ctrl.set_limit("agent-2", "build", 10)
        agents = self.ctrl.list_agents()
        self.assertEqual(agents, ["agent-1", "agent-2"])

    def test_get_stats(self):
        self.ctrl.set_limit("agent-1", "deploy", 5)
        self.ctrl.set_limit("agent-2", "build", 10)
        stats = self.ctrl.get_stats()
        self.assertEqual(stats["total_limits"], 2)
        self.assertEqual(stats["total_agents"], 2)
        self.assertEqual(stats["total_operations"], 2)
        self.assertGreater(stats["seq"], 0)

    def test_reset(self):
        self.ctrl.set_limit("agent-1", "deploy", 5)
        self.ctrl.record_request("agent-1", "deploy")
        self.ctrl.reset()
        self.assertEqual(self.ctrl.get_limit_count(), 0)
        stats = self.ctrl.get_stats()
        self.assertEqual(stats["total_limits"], 0)

    def test_check_rate_after_exceeded(self):
        self.ctrl.set_limit("agent-1", "deploy", 2, 60.0)
        self.ctrl.record_request("agent-1", "deploy")
        self.ctrl.record_request("agent-1", "deploy")
        result = self.ctrl.check_rate("agent-1", "deploy")
        self.assertFalse(result["allowed"])
        self.assertEqual(result["remaining"], 0)

    def test_record_request_no_limit(self):
        self.assertTrue(self.ctrl.record_request("agent-x", "anything"))

    def test_unique_ids(self):
        id1 = self.ctrl.set_limit("agent-1", "deploy", 5)
        id2 = self.ctrl.set_limit("agent-1", "deploy", 5)
        self.assertNotEqual(id1, id2)


if __name__ == "__main__":
    unittest.main()
