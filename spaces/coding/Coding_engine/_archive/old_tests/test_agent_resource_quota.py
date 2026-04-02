import sys
import unittest

sys.path.insert(0, ".")
from src.services.agent_resource_quota import AgentResourceQuota


class TestAgentResourceQuota(unittest.TestCase):
    def setUp(self):
        self.q = AgentResourceQuota()

    def test_set_quota_returns_id(self):
        qid = self.q.set_quota("agent1", "cpu", 100)
        self.assertTrue(qid.startswith("arq-"))
        self.assertEqual(len(qid), 4 + 16)

    def test_consume_within_limit(self):
        self.q.set_quota("agent1", "memory", 10)
        result = self.q.consume("agent1", "memory", 5)
        self.assertTrue(result)

    def test_consume_exceeds_limit(self):
        self.q.set_quota("agent1", "api_calls", 5)
        self.q.consume("agent1", "api_calls", 5)
        result = self.q.consume("agent1", "api_calls", 1)
        self.assertFalse(result)

    def test_consume_no_quota(self):
        result = self.q.consume("agent1", "nonexistent")
        self.assertFalse(result)

    def test_get_usage(self):
        self.q.set_quota("agent1", "cpu", 100)
        self.q.consume("agent1", "cpu", 40)
        usage = self.q.get_usage("agent1", "cpu")
        self.assertEqual(usage["used"], 40)
        self.assertEqual(usage["limit"], 100)
        self.assertEqual(usage["remaining"], 60)
        self.assertAlmostEqual(usage["percent_used"], 40.0)

    def test_get_usage_no_entry(self):
        usage = self.q.get_usage("none", "none")
        self.assertEqual(usage["used"], 0)
        self.assertEqual(usage["limit"], 0)

    def test_release(self):
        self.q.set_quota("agent1", "mem", 50)
        self.q.consume("agent1", "mem", 30)
        result = self.q.release("agent1", "mem", 10)
        self.assertTrue(result)
        usage = self.q.get_usage("agent1", "mem")
        self.assertEqual(usage["used"], 20)

    def test_release_below_zero(self):
        self.q.set_quota("agent1", "mem", 50)
        self.q.consume("agent1", "mem", 5)
        self.q.release("agent1", "mem", 100)
        usage = self.q.get_usage("agent1", "mem")
        self.assertEqual(usage["used"], 0)

    def test_reset_usage(self):
        self.q.set_quota("agent1", "cpu", 100)
        self.q.consume("agent1", "cpu", 80)
        result = self.q.reset_usage("agent1", "cpu")
        self.assertTrue(result)
        usage = self.q.get_usage("agent1", "cpu")
        self.assertEqual(usage["used"], 0)

    def test_get_quotas_and_count(self):
        self.q.set_quota("agent1", "cpu", 100)
        self.q.set_quota("agent1", "mem", 200)
        self.q.set_quota("agent2", "cpu", 50)
        quotas = self.q.get_quotas("agent1")
        self.assertEqual(len(quotas), 2)
        self.assertEqual(self.q.get_quota_count("agent1"), 2)
        self.assertEqual(self.q.get_quota_count(), 3)

    def test_is_within_quota(self):
        self.q.set_quota("agent1", "api", 2)
        self.assertTrue(self.q.is_within_quota("agent1", "api"))
        self.q.consume("agent1", "api", 2)
        self.assertFalse(self.q.is_within_quota("agent1", "api"))

    def test_list_agents(self):
        self.q.set_quota("agent_b", "cpu", 10)
        self.q.set_quota("agent_a", "cpu", 10)
        agents = self.q.list_agents()
        self.assertEqual(agents, ["agent_a", "agent_b"])

    def test_callbacks(self):
        events = []
        self.q.on_change("tracker", lambda action, detail: events.append(action))
        self.q.set_quota("a1", "cpu", 10)
        self.q.consume("a1", "cpu", 1)
        self.assertIn("set_quota", events)
        self.assertIn("consume", events)
        self.assertTrue(self.q.remove_callback("tracker"))
        self.assertFalse(self.q.remove_callback("nonexistent"))

    def test_get_stats(self):
        self.q.set_quota("a1", "cpu", 10)
        stats = self.q.get_stats()
        self.assertEqual(stats["total_entries"], 1)
        self.assertGreater(stats["seq"], 0)

    def test_reset(self):
        self.q.set_quota("a1", "cpu", 10)
        self.q.on_change("cb", lambda a, d: None)
        self.q.reset()
        self.assertEqual(self.q.get_quota_count(), 0)
        stats = self.q.get_stats()
        self.assertEqual(stats["seq"], 0)
        self.assertEqual(stats["callbacks"], 0)

    def test_is_within_quota_no_entry(self):
        self.assertFalse(self.q.is_within_quota("ghost", "cpu"))

    def test_reset_usage_no_entry(self):
        self.assertFalse(self.q.reset_usage("ghost", "cpu"))

    def test_release_no_entry(self):
        self.assertFalse(self.q.release("ghost", "cpu"))


if __name__ == "__main__":
    unittest.main()
