"""Tests for AgentPriorityManager."""

import sys
import unittest

sys.path.insert(0, ".")
from src.services.agent_priority_manager import AgentPriorityManager


class TestAgentPriorityManager(unittest.TestCase):

    def setUp(self):
        self.mgr = AgentPriorityManager()

    def test_set_and_get_priority(self):
        pid = self.mgr.set_priority("agent-1", priority=5, label="high")
        self.assertTrue(pid.startswith("apm-"))
        self.assertEqual(self.mgr.get_priority("agent-1"), 5)

    def test_get_priority_default(self):
        self.assertEqual(self.mgr.get_priority("nonexistent"), 0)

    def test_adjust_priority(self):
        self.mgr.set_priority("agent-1", priority=10)
        new_p = self.mgr.adjust_priority("agent-1", -3)
        self.assertEqual(new_p, 7)
        self.assertEqual(self.mgr.get_priority("agent-1"), 7)

    def test_adjust_priority_creates_entry(self):
        new_p = self.mgr.adjust_priority("agent-new", 5)
        self.assertEqual(new_p, 5)
        self.assertEqual(self.mgr.get_priority("agent-new"), 5)

    def test_get_highest_priority(self):
        self.mgr.set_priority("a1", priority=3)
        self.mgr.set_priority("a2", priority=10)
        self.mgr.set_priority("a3", priority=7)
        top = self.mgr.get_highest_priority(limit=2)
        self.assertEqual(len(top), 2)
        self.assertEqual(top[0]["agent_id"], "a2")
        self.assertEqual(top[1]["agent_id"], "a3")

    def test_get_agents_by_priority(self):
        self.mgr.set_priority("a1", priority=3)
        self.mgr.set_priority("a2", priority=10)
        self.mgr.set_priority("a3", priority=1)
        agents = self.mgr.get_agents_by_priority(min_priority=3)
        self.assertIn("a1", agents)
        self.assertIn("a2", agents)
        self.assertNotIn("a3", agents)

    def test_get_priority_entry(self):
        pid = self.mgr.set_priority("agent-1", priority=5, label="test")
        entry = self.mgr.get_priority_entry(pid)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["agent_id"], "agent-1")
        self.assertEqual(entry["priority"], 5)
        self.assertEqual(entry["label"], "test")

    def test_get_priority_entry_not_found(self):
        self.assertIsNone(self.mgr.get_priority_entry("apm-fake"))

    def test_get_priority_count(self):
        self.assertEqual(self.mgr.get_priority_count(), 0)
        self.mgr.set_priority("a1", priority=1)
        self.mgr.set_priority("a2", priority=2)
        self.assertEqual(self.mgr.get_priority_count(), 2)

    def test_list_agents(self):
        self.mgr.set_priority("a1", priority=1)
        self.mgr.set_priority("a2", priority=2)
        agents = self.mgr.list_agents()
        self.assertEqual(sorted(agents), ["a1", "a2"])

    def test_callbacks(self):
        events = []
        self.mgr.on_change("test_cb", lambda evt, data: events.append((evt, data["agent_id"])))
        self.mgr.set_priority("a1", priority=5)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "set_priority")
        self.assertEqual(events[0][1], "a1")
        # Remove callback
        self.assertTrue(self.mgr.remove_callback("test_cb"))
        self.assertFalse(self.mgr.remove_callback("nonexistent"))
        self.mgr.set_priority("a2", priority=3)
        self.assertEqual(len(events), 1)  # no new events

    def test_get_stats(self):
        stats = self.mgr.get_stats()
        self.assertEqual(stats["total"], 0)
        self.mgr.set_priority("a1", priority=2)
        self.mgr.set_priority("a2", priority=8)
        stats = self.mgr.get_stats()
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["min_priority"], 2)
        self.assertEqual(stats["max_priority"], 8)
        self.assertEqual(stats["avg_priority"], 5.0)
        self.assertEqual(stats["unique_agents"], 2)

    def test_reset(self):
        self.mgr.set_priority("a1", priority=5)
        self.mgr.on_change("cb", lambda e, d: None)
        self.mgr.reset()
        self.assertEqual(self.mgr.get_priority_count(), 0)
        self.assertEqual(self.mgr.get_priority("a1"), 0)

    def test_unique_ids(self):
        id1 = self.mgr.set_priority("a1", priority=1)
        id2 = self.mgr.set_priority("a2", priority=2)
        self.assertNotEqual(id1, id2)

    def test_prune_max_entries(self):
        mgr = AgentPriorityManager()
        for i in range(10005):
            mgr.set_priority(f"agent-{i}", priority=i)
        self.assertLessEqual(mgr.get_priority_count(), 10000)


if __name__ == "__main__":
    unittest.main()
