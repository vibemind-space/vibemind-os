"""Tests for AgentCapabilityProfile."""

import sys
import unittest

sys.path.insert(0, ".")
from src.services.agent_capability_profile import AgentCapabilityProfile


class TestAgentCapabilityProfile(unittest.TestCase):
    def setUp(self):
        self.acp = AgentCapabilityProfile()

    def test_create_profile_basic(self):
        pid = self.acp.create_profile("agent-1")
        self.assertTrue(pid.startswith("acp2-"))
        self.assertEqual(self.acp.get_profile_count(), 1)

    def test_create_profile_with_capabilities(self):
        caps = {"coding": 0.9, "testing": 0.7}
        pid = self.acp.create_profile("agent-2", capabilities=caps)
        profile = self.acp.get_profile("agent-2")
        self.assertIsNotNone(profile)
        self.assertAlmostEqual(profile["capabilities"]["coding"], 0.9)
        self.assertAlmostEqual(profile["capabilities"]["testing"], 0.7)

    def test_add_capability(self):
        self.acp.create_profile("agent-3")
        result = self.acp.add_capability("agent-3", "debugging", 0.8)
        self.assertTrue(result)
        level = self.acp.get_capability("agent-3", "debugging")
        self.assertAlmostEqual(level, 0.8)

    def test_add_capability_nonexistent_agent(self):
        result = self.acp.add_capability("no-agent", "coding")
        self.assertFalse(result)

    def test_remove_capability(self):
        self.acp.create_profile("agent-4", capabilities={"coding": 0.5})
        result = self.acp.remove_capability("agent-4", "coding")
        self.assertTrue(result)
        self.assertIsNone(self.acp.get_capability("agent-4", "coding"))

    def test_remove_capability_not_found(self):
        self.acp.create_profile("agent-5")
        result = self.acp.remove_capability("agent-5", "nonexistent")
        self.assertFalse(result)

    def test_update_skill_level(self):
        self.acp.create_profile("agent-6", capabilities={"coding": 0.5})
        result = self.acp.update_skill_level("agent-6", "coding", 0.95)
        self.assertTrue(result)
        self.assertAlmostEqual(self.acp.get_capability("agent-6", "coding"), 0.95)

    def test_update_skill_level_nonexistent_capability(self):
        self.acp.create_profile("agent-7")
        result = self.acp.update_skill_level("agent-7", "nonexistent", 0.5)
        self.assertFalse(result)

    def test_match_requirements_all_met(self):
        self.acp.create_profile("agent-8", capabilities={"coding": 0.9, "testing": 0.8})
        result = self.acp.match_requirements("agent-8", {"coding": 0.7, "testing": 0.6})
        self.assertTrue(result["matches"])
        self.assertEqual(len(result["met"]), 2)
        self.assertEqual(len(result["unmet"]), 0)
        self.assertAlmostEqual(result["score"], 1.0)

    def test_match_requirements_partial(self):
        self.acp.create_profile("agent-9", capabilities={"coding": 0.9})
        result = self.acp.match_requirements("agent-9", {"coding": 0.5, "testing": 0.5})
        self.assertFalse(result["matches"])
        self.assertIn("coding", result["met"])
        self.assertIn("testing", result["unmet"])
        self.assertAlmostEqual(result["score"], 0.5)

    def test_match_requirements_nonexistent_agent(self):
        result = self.acp.match_requirements("no-agent", {"coding": 0.5})
        self.assertFalse(result["matches"])
        self.assertEqual(result["score"], 0.0)

    def test_list_agents(self):
        self.acp.create_profile("a1")
        self.acp.create_profile("a2")
        agents = self.acp.list_agents()
        self.assertIn("a1", agents)
        self.assertIn("a2", agents)
        self.assertEqual(len(agents), 2)

    def test_get_stats(self):
        self.acp.create_profile("s1", capabilities={"c1": 0.5, "c2": 0.6})
        stats = self.acp.get_stats()
        self.assertEqual(stats["profile_count"], 1)
        self.assertEqual(stats["total_capabilities"], 2)

    def test_reset(self):
        self.acp.create_profile("r1")
        self.acp.reset()
        self.assertEqual(self.acp.get_profile_count(), 0)
        self.assertIsNone(self.acp.get_profile("r1"))

    def test_callbacks(self):
        events = []
        self.acp.on_change("test_cb", lambda action, detail: events.append(action))
        self.acp.create_profile("cb-agent")
        self.assertIn("create_profile", events)
        removed = self.acp.remove_callback("test_cb")
        self.assertTrue(removed)
        removed2 = self.acp.remove_callback("test_cb")
        self.assertFalse(removed2)

    def test_skill_level_clamping(self):
        self.acp.create_profile("clamp", capabilities={"over": 1.5, "under": -0.5})
        self.assertAlmostEqual(self.acp.get_capability("clamp", "over"), 1.0)
        self.assertAlmostEqual(self.acp.get_capability("clamp", "under"), 0.0)

    def test_unique_ids(self):
        id1 = self.acp.create_profile("u1")
        id2 = self.acp.create_profile("u2")
        self.assertNotEqual(id1, id2)

    def test_get_profile_nonexistent(self):
        self.assertIsNone(self.acp.get_profile("nonexistent"))

    def test_get_capability_nonexistent_agent(self):
        self.assertIsNone(self.acp.get_capability("nonexistent", "coding"))


if __name__ == "__main__":
    unittest.main()
