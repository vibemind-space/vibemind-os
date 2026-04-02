"""Tests for AgentActionRecorder."""

import sys
import unittest

sys.path.insert(0, ".")
from src.services.agent_action_recorder import AgentActionRecorder


class TestAgentActionRecorder(unittest.TestCase):

    def setUp(self):
        self.recorder = AgentActionRecorder()

    def test_record_action_returns_id(self):
        action_id = self.recorder.record_action("agent-1", "click", params={"x": 10})
        self.assertTrue(action_id.startswith("aar2-"))
        self.assertEqual(len(action_id), 5 + 16)  # prefix + hash

    def test_get_action(self):
        action_id = self.recorder.record_action("agent-1", "click", params={"x": 1}, result="ok")
        action = self.recorder.get_action(action_id)
        self.assertIsNotNone(action)
        self.assertEqual(action["agent_id"], "agent-1")
        self.assertEqual(action["action_type"], "click")
        self.assertEqual(action["params"], {"x": 1})
        self.assertEqual(action["result"], "ok")

    def test_get_action_not_found(self):
        self.assertIsNone(self.recorder.get_action("aar2-nonexistent"))

    def test_get_actions_filters_by_agent(self):
        self.recorder.record_action("agent-1", "click")
        self.recorder.record_action("agent-2", "type")
        self.recorder.record_action("agent-1", "scroll")
        actions = self.recorder.get_actions("agent-1")
        self.assertEqual(len(actions), 2)
        self.assertTrue(all(a["agent_id"] == "agent-1" for a in actions))

    def test_get_actions_filters_by_type(self):
        self.recorder.record_action("agent-1", "click")
        self.recorder.record_action("agent-1", "type")
        self.recorder.record_action("agent-1", "click")
        actions = self.recorder.get_actions("agent-1", action_type="click")
        self.assertEqual(len(actions), 2)

    def test_get_actions_limit(self):
        for i in range(10):
            self.recorder.record_action("agent-1", "step")
        actions = self.recorder.get_actions("agent-1", limit=3)
        self.assertEqual(len(actions), 3)

    def test_get_latest_action(self):
        self.recorder.record_action("agent-1", "first")
        self.recorder.record_action("agent-1", "second")
        self.recorder.record_action("agent-1", "third")
        latest = self.recorder.get_latest_action("agent-1")
        self.assertIsNotNone(latest)
        self.assertEqual(latest["action_type"], "third")

    def test_get_latest_action_no_actions(self):
        self.assertIsNone(self.recorder.get_latest_action("agent-x"))

    def test_get_action_sequence(self):
        self.recorder.record_action("agent-1", "a")
        self.recorder.record_action("agent-1", "b")
        self.recorder.record_action("agent-1", "c")
        self.recorder.record_action("agent-1", "d")
        seq = self.recorder.get_action_sequence("agent-1", from_index=1, to_index=3)
        self.assertEqual(len(seq), 2)
        self.assertEqual(seq[0]["action_type"], "b")
        self.assertEqual(seq[1]["action_type"], "c")

    def test_get_action_sequence_default(self):
        self.recorder.record_action("agent-1", "a")
        self.recorder.record_action("agent-1", "b")
        seq = self.recorder.get_action_sequence("agent-1")
        self.assertEqual(len(seq), 2)

    def test_get_action_count(self):
        self.recorder.record_action("agent-1", "a")
        self.recorder.record_action("agent-2", "b")
        self.recorder.record_action("agent-1", "c")
        self.assertEqual(self.recorder.get_action_count(), 3)
        self.assertEqual(self.recorder.get_action_count("agent-1"), 2)
        self.assertEqual(self.recorder.get_action_count("agent-2"), 1)

    def test_clear_actions(self):
        self.recorder.record_action("agent-1", "a")
        self.recorder.record_action("agent-2", "b")
        result = self.recorder.clear_actions("agent-1")
        self.assertTrue(result)
        self.assertEqual(self.recorder.get_action_count("agent-1"), 0)
        self.assertEqual(self.recorder.get_action_count("agent-2"), 1)

    def test_clear_actions_nonexistent(self):
        self.assertFalse(self.recorder.clear_actions("no-agent"))

    def test_list_agents(self):
        self.recorder.record_action("agent-b", "x")
        self.recorder.record_action("agent-a", "x")
        self.recorder.record_action("agent-b", "y")
        agents = self.recorder.list_agents()
        self.assertEqual(agents, ["agent-a", "agent-b"])

    def test_get_stats(self):
        self.recorder.record_action("agent-1", "a")
        self.recorder.record_action("agent-2", "b")
        stats = self.recorder.get_stats()
        self.assertEqual(stats["total_actions"], 2)
        self.assertEqual(stats["total_agents"], 2)
        self.assertIn("agent-1", stats["agents"])

    def test_reset(self):
        self.recorder.record_action("agent-1", "a")
        self.recorder.on_change("cb1", lambda e, d: None)
        self.recorder.reset()
        self.assertEqual(self.recorder.get_action_count(), 0)
        self.assertEqual(self.recorder.list_agents(), [])

    def test_callbacks(self):
        events = []
        self.recorder.on_change("cb1", lambda e, d: events.append((e, d)))
        self.recorder.record_action("agent-1", "click")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "action_recorded")
        # remove callback
        self.assertTrue(self.recorder.remove_callback("cb1"))
        self.assertFalse(self.recorder.remove_callback("cb1"))
        self.recorder.record_action("agent-1", "click")
        self.assertEqual(len(events), 1)  # no new event

    def test_prune_max_entries(self):
        recorder = AgentActionRecorder()
        recorder.MAX_ENTRIES = 100
        for i in range(150):
            recorder.record_action("agent-1", f"action-{i}")
        self.assertLessEqual(len(recorder._state.entries), 100)

    def test_unique_ids(self):
        ids = set()
        for i in range(50):
            aid = self.recorder.record_action("agent-1", "action")
            ids.add(aid)
        self.assertEqual(len(ids), 50)


if __name__ == "__main__":
    unittest.main()
