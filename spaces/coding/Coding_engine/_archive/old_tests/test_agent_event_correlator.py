"""Tests for AgentEventCorrelator."""

import sys
import unittest
import time

sys.path.insert(0, ".")
from src.services.agent_event_correlator import AgentEventCorrelator, AgentEventCorrelatorState


class TestAgentEventCorrelator(unittest.TestCase):

    def setUp(self):
        self.correlator = AgentEventCorrelator()

    def test_add_event_returns_id_with_prefix(self):
        eid = self.correlator.add_event("agent-1", "task_start")
        self.assertTrue(eid.startswith("aec2-"))

    def test_add_event_stores_event(self):
        eid = self.correlator.add_event("agent-1", "task_start", payload={"key": "val"})
        events = self.correlator.get_events(agent_id="agent-1")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_id"], eid)
        self.assertEqual(events[0]["payload"], {"key": "val"})

    def test_get_events_filter_by_type(self):
        self.correlator.add_event("agent-1", "start")
        self.correlator.add_event("agent-1", "stop")
        self.correlator.add_event("agent-2", "start")
        result = self.correlator.get_events(event_type="start")
        self.assertEqual(len(result), 2)

    def test_get_events_filter_by_agent_and_type(self):
        self.correlator.add_event("agent-1", "start")
        self.correlator.add_event("agent-1", "stop")
        self.correlator.add_event("agent-2", "start")
        result = self.correlator.get_events(agent_id="agent-1", event_type="start")
        self.assertEqual(len(result), 1)

    def test_get_event_count(self):
        self.correlator.add_event("agent-1", "start")
        self.correlator.add_event("agent-1", "stop")
        self.correlator.add_event("agent-2", "start")
        self.assertEqual(self.correlator.get_event_count(), 3)
        self.assertEqual(self.correlator.get_event_count(agent_id="agent-1"), 2)

    def test_list_agents(self):
        self.correlator.add_event("agent-b", "x")
        self.correlator.add_event("agent-a", "x")
        self.correlator.add_event("agent-b", "y")
        agents = self.correlator.list_agents()
        self.assertEqual(agents, ["agent-a", "agent-b"])

    def test_create_and_get_rule(self):
        rid = self.correlator.create_rule("test_rule", ["start", "stop"], time_window_seconds=30.0)
        self.assertTrue(rid.startswith("aec2-"))
        rule = self.correlator.get_rule(rid)
        self.assertIsNotNone(rule)
        self.assertEqual(rule["rule_name"], "test_rule")
        self.assertEqual(rule["event_types"], ["start", "stop"])
        self.assertEqual(rule["time_window_seconds"], 30.0)

    def test_get_rules(self):
        self.correlator.create_rule("r1", ["a"])
        self.correlator.create_rule("r2", ["b"])
        rules = self.correlator.get_rules()
        self.assertEqual(len(rules), 2)

    def test_remove_rule(self):
        rid = self.correlator.create_rule("r1", ["a"])
        self.assertTrue(self.correlator.remove_rule(rid))
        self.assertIsNone(self.correlator.get_rule(rid))
        self.assertFalse(self.correlator.remove_rule("nonexistent"))

    def test_find_correlations(self):
        t = 1000.0
        self.correlator.add_event("agent-1", "login", timestamp=t)
        self.correlator.add_event("agent-2", "login", timestamp=t + 5)
        self.correlator.add_event("agent-1", "error", timestamp=t + 10)
        rid = self.correlator.create_rule("login_error", ["login", "error"], time_window_seconds=60.0)
        corrs = self.correlator.find_correlations(rid)
        self.assertGreaterEqual(len(corrs), 1)
        self.assertEqual(corrs[0]["rule_id"], rid)
        self.assertIn("events", corrs[0])

    def test_find_correlations_no_match(self):
        t = 1000.0
        self.correlator.add_event("agent-1", "login", timestamp=t)
        self.correlator.add_event("agent-1", "error", timestamp=t + 200)
        rid = self.correlator.create_rule("login_error", ["login", "error"], time_window_seconds=10.0)
        corrs = self.correlator.find_correlations(rid)
        self.assertEqual(len(corrs), 0)

    def test_find_correlations_unknown_rule(self):
        self.assertEqual(self.correlator.find_correlations("nonexistent"), [])

    def test_callbacks(self):
        changes = []
        self.correlator.on_change("cb1", lambda name, data: changes.append(name))
        self.correlator.add_event("a", "b")
        self.assertIn("event_added", changes)

    def test_remove_callback(self):
        self.correlator.on_change("cb1", lambda n, d: None)
        self.assertTrue(self.correlator.remove_callback("cb1"))
        self.assertFalse(self.correlator.remove_callback("cb1"))

    def test_get_stats(self):
        self.correlator.add_event("agent-1", "x")
        self.correlator.create_rule("r1", ["x"])
        stats = self.correlator.get_stats()
        self.assertEqual(stats["total_events"], 1)
        self.assertEqual(stats["total_rules"], 1)
        self.assertIn("agent-1", stats["agents"])

    def test_reset(self):
        self.correlator.add_event("agent-1", "x")
        self.correlator.create_rule("r1", ["x"])
        self.correlator.reset()
        self.assertEqual(self.correlator.get_event_count(), 0)
        self.assertEqual(self.correlator.get_rules(), [])

    def test_prune_at_max(self):
        for i in range(10050):
            self.correlator.add_event("a", "t", timestamp=float(i))
        self.assertLessEqual(len(self.correlator._events), 10000)

    def test_unique_ids(self):
        ids = set()
        for i in range(100):
            eid = self.correlator.add_event("a", "t", timestamp=float(i))
            ids.add(eid)
        self.assertEqual(len(ids), 100)

    def test_state_dataclass(self):
        state = AgentEventCorrelatorState()
        self.assertEqual(state.entries, {})
        self.assertEqual(state._seq, 0)

    def test_default_timestamp(self):
        before = time.time()
        self.correlator.add_event("a", "t")
        after = time.time()
        events = self.correlator.get_events()
        self.assertGreaterEqual(events[0]["timestamp"], before)
        self.assertLessEqual(events[0]["timestamp"], after)


if __name__ == "__main__":
    unittest.main()
