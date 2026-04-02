"""Tests for AgentStateHistory."""

import sys
import time
import unittest

sys.path.insert(0, ".")
from src.services.agent_state_history import AgentStateHistory


class TestAgentStateHistory(unittest.TestCase):

    def setUp(self):
        self.history = AgentStateHistory()

    def test_record_state_returns_id(self):
        entry_id = self.history.record_state("agent-1", "idle")
        self.assertTrue(entry_id.startswith("ash-"))
        self.assertEqual(len(entry_id), 4 + 16)  # "ash-" + 16 hex chars

    def test_get_current_state(self):
        self.assertIsNone(self.history.get_current_state("agent-1"))
        self.history.record_state("agent-1", "idle")
        self.assertEqual(self.history.get_current_state("agent-1"), "idle")
        self.history.record_state("agent-1", "running")
        self.assertEqual(self.history.get_current_state("agent-1"), "running")

    def test_get_history_newest_first(self):
        self.history.record_state("agent-1", "idle")
        self.history.record_state("agent-1", "running")
        self.history.record_state("agent-1", "done")
        history = self.history.get_history("agent-1")
        self.assertEqual(len(history), 3)
        self.assertEqual(history[0]["state"], "done")
        self.assertEqual(history[2]["state"], "idle")

    def test_get_history_limit(self):
        for i in range(10):
            self.history.record_state("agent-1", f"state-{i}")
        history = self.history.get_history("agent-1", limit=3)
        self.assertEqual(len(history), 3)
        self.assertEqual(history[0]["state"], "state-9")

    def test_get_transitions_filter(self):
        self.history.record_state("agent-1", "idle")
        self.history.record_state("agent-1", "running")
        self.history.record_state("agent-1", "idle")
        self.history.record_state("agent-1", "error")

        transitions = self.history.get_transitions("agent-1", from_state="idle")
        self.assertEqual(len(transitions), 2)
        for t in transitions:
            self.assertEqual(t["previous_state"], "idle")

        transitions = self.history.get_transitions("agent-1", to_state="idle")
        self.assertEqual(len(transitions), 1)
        self.assertEqual(transitions[0]["state"], "idle")
        self.assertEqual(transitions[0]["previous_state"], "running")

    def test_get_state_duration(self):
        self.history.record_state("agent-1", "idle")
        time.sleep(0.05)
        self.history.record_state("agent-1", "running")
        time.sleep(0.05)
        self.history.record_state("agent-1", "done")

        duration = self.history.get_state_duration("agent-1", "idle")
        self.assertGreater(duration, 0.04)
        self.assertLess(duration, 0.2)

        duration_running = self.history.get_state_duration("agent-1", "running")
        self.assertGreater(duration_running, 0.04)

    def test_get_entry(self):
        entry_id = self.history.record_state("agent-1", "idle", reason="startup")
        entry = self.history.get_entry(entry_id)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["agent_id"], "agent-1")
        self.assertEqual(entry["state"], "idle")
        self.assertEqual(entry["reason"], "startup")
        self.assertIsNone(self.history.get_entry("ash-nonexistent1234"))

    def test_get_entry_count(self):
        self.assertEqual(self.history.get_entry_count(), 0)
        self.history.record_state("agent-1", "idle")
        self.history.record_state("agent-2", "idle")
        self.history.record_state("agent-1", "running")
        self.assertEqual(self.history.get_entry_count(), 3)
        self.assertEqual(self.history.get_entry_count("agent-1"), 2)
        self.assertEqual(self.history.get_entry_count("agent-2"), 1)

    def test_list_agents(self):
        self.assertEqual(self.history.list_agents(), [])
        self.history.record_state("agent-b", "idle")
        self.history.record_state("agent-a", "idle")
        self.assertEqual(self.history.list_agents(), ["agent-a", "agent-b"])

    def test_callbacks(self):
        events = []
        self.history.on_change("test_cb", lambda event, **kw: events.append((event, kw)))
        self.history.record_state("agent-1", "idle")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "state_recorded")
        self.assertIn("entry", events[0][1])

        self.assertTrue(self.history.remove_callback("test_cb"))
        self.assertFalse(self.history.remove_callback("test_cb"))
        self.history.record_state("agent-1", "running")
        self.assertEqual(len(events), 1)  # no new callback fired

    def test_get_stats(self):
        self.history.record_state("agent-1", "idle")
        self.history.record_state("agent-2", "running")
        stats = self.history.get_stats()
        self.assertEqual(stats["total_entries"], 2)
        self.assertEqual(stats["agent_count"], 2)
        self.assertIn("agent-1", stats["agents"])
        self.assertGreater(stats["seq"], 0)

    def test_reset(self):
        self.history.on_change("cb1", lambda e, **kw: None)
        self.history.record_state("agent-1", "idle")
        self.history.reset()
        self.assertEqual(self.history.get_entry_count(), 0)
        self.assertEqual(self.history.list_agents(), [])
        self.assertEqual(self.history.get_stats()["seq"], 0)

    def test_prune_max_entries(self):
        old_max = AgentStateHistory.MAX_ENTRIES
        AgentStateHistory.MAX_ENTRIES = 10
        try:
            for i in range(15):
                self.history.record_state("agent-1", f"state-{i}")
            self.assertEqual(self.history.get_entry_count(), 10)
        finally:
            AgentStateHistory.MAX_ENTRIES = old_max

    def test_unique_ids(self):
        ids = set()
        for i in range(100):
            entry_id = self.history.record_state("agent-1", f"state-{i % 5}")
            ids.add(entry_id)
        self.assertEqual(len(ids), 100)

    def test_previous_state_tracking(self):
        self.history.record_state("agent-1", "idle")
        self.history.record_state("agent-1", "running")
        history = self.history.get_history("agent-1")
        self.assertEqual(history[0]["previous_state"], "idle")
        self.assertIsNone(history[1]["previous_state"])


if __name__ == "__main__":
    unittest.main()
