"""Tests for AgentWorkflowTrigger."""

import sys
import unittest

sys.path.insert(0, ".")
from src.services.agent_workflow_trigger import AgentWorkflowTrigger


class TestAgentWorkflowTrigger(unittest.TestCase):
    def setUp(self):
        self.trigger = AgentWorkflowTrigger()

    def test_register_trigger_returns_id(self):
        tid = self.trigger.register_trigger("agent1", "on_start")
        self.assertTrue(tid.startswith("awt-"))
        self.assertEqual(len(tid), 4 + 16)

    def test_register_trigger_default_type_manual(self):
        tid = self.trigger.register_trigger("agent1", "on_start")
        entry = self.trigger.get_trigger(tid)
        self.assertEqual(entry["trigger_type"], "manual")

    def test_get_trigger_not_found(self):
        self.assertIsNone(self.trigger.get_trigger("awt-nonexistent"))

    def test_evaluate_manual_trigger(self):
        self.trigger.register_trigger("a1", "go")
        result = self.trigger.evaluate_trigger("a1", "go")
        self.assertTrue(result["triggered"])
        self.assertEqual(result["trigger_type"], "manual")

    def test_evaluate_condition_trigger_true(self):
        self.trigger.register_trigger(
            "a1", "cond", trigger_type="condition", condition={"status": "ready"}
        )
        result = self.trigger.evaluate_trigger("a1", "cond", context={"status": "ready"})
        self.assertTrue(result["triggered"])

    def test_evaluate_condition_trigger_false(self):
        self.trigger.register_trigger(
            "a1", "cond", trigger_type="condition", condition={"status": "ready"}
        )
        result = self.trigger.evaluate_trigger("a1", "cond", context={"status": "pending"})
        self.assertFalse(result["triggered"])

    def test_evaluate_nonexistent_trigger(self):
        result = self.trigger.evaluate_trigger("noagent", "notrig")
        self.assertFalse(result["triggered"])
        self.assertIsNone(result["trigger_id"])

    def test_fire_trigger(self):
        tid = self.trigger.register_trigger("a1", "t1")
        res = self.trigger.fire_trigger(tid)
        self.assertEqual(res["fire_count"], 1)
        self.assertIsNotNone(res["fired_at"])
        res2 = self.trigger.fire_trigger(tid)
        self.assertEqual(res2["fire_count"], 2)

    def test_fire_nonexistent_trigger(self):
        res = self.trigger.fire_trigger("awt-nope")
        self.assertEqual(res["fire_count"], 0)
        self.assertIsNone(res["fired_at"])

    def test_remove_trigger(self):
        tid = self.trigger.register_trigger("a1", "t1")
        self.assertTrue(self.trigger.remove_trigger(tid))
        self.assertIsNone(self.trigger.get_trigger(tid))
        self.assertFalse(self.trigger.remove_trigger(tid))

    def test_get_triggers_by_agent(self):
        self.trigger.register_trigger("a1", "t1")
        self.trigger.register_trigger("a1", "t2", trigger_type="event")
        self.trigger.register_trigger("a2", "t3")
        self.assertEqual(len(self.trigger.get_triggers("a1")), 2)
        self.assertEqual(len(self.trigger.get_triggers("a1", trigger_type="event")), 1)
        self.assertEqual(len(self.trigger.get_triggers("a2")), 1)

    def test_get_trigger_count(self):
        self.trigger.register_trigger("a1", "t1")
        self.trigger.register_trigger("a2", "t2")
        self.assertEqual(self.trigger.get_trigger_count(), 2)
        self.assertEqual(self.trigger.get_trigger_count("a1"), 1)

    def test_list_agents(self):
        self.trigger.register_trigger("b", "t")
        self.trigger.register_trigger("a", "t")
        self.assertEqual(self.trigger.list_agents(), ["a", "b"])

    def test_callbacks(self):
        events = []
        self.trigger.on_change("test_cb", lambda action, detail: events.append(action))
        self.trigger.register_trigger("a1", "t1")
        self.assertIn("register_trigger", events)
        self.assertTrue(self.trigger.remove_callback("test_cb"))
        self.assertFalse(self.trigger.remove_callback("test_cb"))

    def test_get_stats(self):
        self.trigger.register_trigger("a1", "t1")
        tid = self.trigger.register_trigger("a1", "t2")
        self.trigger.fire_trigger(tid)
        stats = self.trigger.get_stats()
        self.assertEqual(stats["total_triggers"], 2)
        self.assertEqual(stats["total_fires"], 1)
        self.assertEqual(stats["seq"], 2)

    def test_reset(self):
        self.trigger.register_trigger("a1", "t1")
        self.trigger.on_change("cb", lambda a, d: None)
        self.trigger.reset()
        self.assertEqual(self.trigger.get_trigger_count(), 0)
        stats = self.trigger.get_stats()
        self.assertEqual(stats["total_triggers"], 0)

    def test_evaluate_event_and_schedule_types(self):
        self.trigger.register_trigger("a1", "ev", trigger_type="event")
        self.trigger.register_trigger("a1", "sc", trigger_type="schedule")
        r1 = self.trigger.evaluate_trigger("a1", "ev")
        r2 = self.trigger.evaluate_trigger("a1", "sc")
        self.assertTrue(r1["triggered"])
        self.assertTrue(r2["triggered"])


if __name__ == "__main__":
    unittest.main()
