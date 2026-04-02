"""Tests for AgentResourceCounter."""

import sys
import unittest

sys.path.insert(0, ".")
from src.services.agent_resource_counter import AgentResourceCounter


class TestAgentResourceCounter(unittest.TestCase):

    def setUp(self):
        self.counter = AgentResourceCounter()

    def test_increment(self):
        result = self.counter.increment("agent-1", "api_calls")
        self.assertEqual(result, 1)
        result = self.counter.increment("agent-1", "api_calls", 5)
        self.assertEqual(result, 6)

    def test_decrement(self):
        self.counter.increment("agent-1", "tokens", 10)
        result = self.counter.decrement("agent-1", "tokens", 3)
        self.assertEqual(result, 7)

    def test_decrement_min_zero(self):
        self.counter.increment("agent-1", "tokens", 2)
        result = self.counter.decrement("agent-1", "tokens", 10)
        self.assertEqual(result, 0)

    def test_get_count(self):
        self.assertEqual(self.counter.get_count("agent-1", "ops"), 0)
        self.counter.increment("agent-1", "ops", 42)
        self.assertEqual(self.counter.get_count("agent-1", "ops"), 42)

    def test_get_all_counts(self):
        self.counter.increment("agent-1", "api_calls", 5)
        self.counter.increment("agent-1", "tokens", 100)
        self.counter.increment("agent-2", "api_calls", 3)
        counts = self.counter.get_all_counts("agent-1")
        self.assertEqual(counts, {"api_calls": 5, "tokens": 100})

    def test_reset_count(self):
        self.counter.increment("agent-1", "ops", 10)
        self.assertTrue(self.counter.reset_count("agent-1", "ops"))
        self.assertEqual(self.counter.get_count("agent-1", "ops"), 0)
        self.assertFalse(self.counter.reset_count("agent-1", "ops"))

    def test_get_top_consumers(self):
        self.counter.increment("agent-1", "api_calls", 10)
        self.counter.increment("agent-2", "api_calls", 50)
        self.counter.increment("agent-3", "api_calls", 30)
        top = self.counter.get_top_consumers("api_calls", limit=2)
        self.assertEqual(len(top), 2)
        self.assertEqual(top[0]["agent_id"], "agent-2")
        self.assertEqual(top[0]["count"], 50)
        self.assertEqual(top[1]["agent_id"], "agent-3")

    def test_get_counter_count(self):
        self.counter.increment("agent-1", "api_calls")
        self.counter.increment("agent-1", "tokens")
        self.counter.increment("agent-2", "api_calls")
        self.assertEqual(self.counter.get_counter_count(), 3)
        self.assertEqual(self.counter.get_counter_count("agent-1"), 2)

    def test_list_agents(self):
        self.counter.increment("agent-b", "ops")
        self.counter.increment("agent-a", "ops")
        self.assertEqual(self.counter.list_agents(), ["agent-a", "agent-b"])

    def test_list_resources(self):
        self.counter.increment("agent-1", "tokens")
        self.counter.increment("agent-1", "api_calls")
        self.assertEqual(self.counter.list_resources(), ["api_calls", "tokens"])

    def test_callbacks(self):
        events = []
        cb_id = self.counter.on_change(lambda etype, data: events.append((etype, data)))
        self.assertTrue(cb_id.startswith("arco2-"))
        self.counter.increment("agent-1", "ops")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "increment")
        self.assertTrue(self.counter.remove_callback(cb_id))
        self.assertFalse(self.counter.remove_callback(cb_id))
        self.counter.increment("agent-1", "ops")
        self.assertEqual(len(events), 1)

    def test_get_stats(self):
        self.counter.increment("agent-1", "ops", 5)
        stats = self.counter.get_stats()
        self.assertEqual(stats["total_entries"], 1)
        self.assertEqual(stats["total_agents"], 1)
        self.assertIn("created_at", stats)

    def test_reset(self):
        self.counter.increment("agent-1", "ops", 5)
        self.counter.on_change(lambda e, d: None)
        self.counter.reset()
        self.assertEqual(self.counter.get_counter_count(), 0)
        self.assertEqual(self.counter.state._seq, 0)
        self.assertEqual(len(self.counter.callbacks), 0)

    def test_prune_max_entries(self):
        for i in range(10050):
            self.counter.increment(f"agent-{i}", "ops")
        self.assertLessEqual(len(self.counter.state.entries), 10000)

    def test_id_prefix(self):
        cb_id = self.counter.on_change(lambda e, d: None)
        self.assertTrue(cb_id.startswith("arco2-"))


if __name__ == "__main__":
    unittest.main()
