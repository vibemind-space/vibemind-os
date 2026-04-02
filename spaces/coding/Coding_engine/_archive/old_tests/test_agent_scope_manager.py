"""Tests for AgentScopeManager."""

import sys
import unittest

sys.path.insert(0, ".")
from src.services.agent_scope_manager import AgentScopeManager


class TestAgentScopeManager(unittest.TestCase):

    def setUp(self):
        self.mgr = AgentScopeManager()

    def test_create_scope_returns_id(self):
        sid = self.mgr.create_scope("a1", "global")
        self.assertTrue(sid.startswith("asm-"))
        self.assertEqual(len(sid), 4 + 16)

    def test_get_scope(self):
        sid = self.mgr.create_scope("a1", "work", parent_scope="root")
        scope = self.mgr.get_scope(sid)
        self.assertIsNotNone(scope)
        self.assertEqual(scope["agent_id"], "a1")
        self.assertEqual(scope["scope_name"], "work")
        self.assertEqual(scope["parent_scope"], "root")

    def test_get_scope_not_found(self):
        self.assertIsNone(self.mgr.get_scope("asm-doesnotexist"))

    def test_enter_and_exit_scope(self):
        self.mgr.create_scope("a1", "outer")
        self.mgr.create_scope("a1", "inner")
        self.assertTrue(self.mgr.enter_scope("a1", "outer"))
        self.assertEqual(self.mgr.get_active_scope("a1"), "outer")
        self.assertTrue(self.mgr.enter_scope("a1", "inner"))
        self.assertEqual(self.mgr.get_active_scope("a1"), "inner")
        parent = self.mgr.exit_scope("a1")
        self.assertEqual(parent, "outer")
        self.assertEqual(self.mgr.get_active_scope("a1"), "outer")
        parent2 = self.mgr.exit_scope("a1")
        self.assertEqual(parent2, "")

    def test_enter_scope_nonexistent(self):
        self.assertFalse(self.mgr.enter_scope("a1", "nope"))

    def test_exit_scope_empty_stack(self):
        self.assertEqual(self.mgr.exit_scope("a1"), "")

    def test_set_and_get_variable(self):
        self.mgr.create_scope("a1", "s1")
        self.mgr.enter_scope("a1", "s1")
        self.assertTrue(self.mgr.set_variable("a1", "x", 42))
        self.assertEqual(self.mgr.get_variable("a1", "x"), 42)

    def test_get_variable_scope_chain(self):
        self.mgr.create_scope("a1", "parent_s")
        self.mgr.create_scope("a1", "child_s")
        self.mgr.enter_scope("a1", "parent_s")
        self.mgr.set_variable("a1", "shared", "from_parent")
        self.mgr.enter_scope("a1", "child_s")
        # child has no 'shared', should find in parent
        self.assertEqual(self.mgr.get_variable("a1", "shared"), "from_parent")
        # child override
        self.mgr.set_variable("a1", "shared", "from_child")
        self.assertEqual(self.mgr.get_variable("a1", "shared"), "from_child")

    def test_get_variable_not_found(self):
        self.assertIsNone(self.mgr.get_variable("a1", "missing"))

    def test_set_variable_no_active_scope(self):
        self.assertFalse(self.mgr.set_variable("a1", "k", "v"))

    def test_get_scopes_and_count(self):
        self.mgr.create_scope("a1", "s1")
        self.mgr.create_scope("a1", "s2")
        self.mgr.create_scope("a2", "s3")
        self.assertEqual(len(self.mgr.get_scopes("a1")), 2)
        self.assertEqual(self.mgr.get_scope_count("a1"), 2)
        self.assertEqual(self.mgr.get_scope_count("a2"), 1)
        self.assertEqual(self.mgr.get_scope_count(), 3)

    def test_list_agents(self):
        self.mgr.create_scope("b", "s")
        self.mgr.create_scope("a", "s")
        self.assertEqual(self.mgr.list_agents(), ["a", "b"])

    def test_callbacks(self):
        events = []
        self.mgr.on_change("cb1", lambda evt, d: events.append(evt))
        self.mgr.create_scope("a1", "s1")
        self.assertIn("scope_created", events)
        self.assertTrue(self.mgr.remove_callback("cb1"))
        self.assertFalse(self.mgr.remove_callback("cb1"))

    def test_get_stats(self):
        self.mgr.create_scope("a1", "s1")
        stats = self.mgr.get_stats()
        self.assertEqual(stats["total_scopes"], 1)
        self.assertEqual(stats["total_agents"], 1)
        self.assertIn("seq", stats)

    def test_reset(self):
        self.mgr.create_scope("a1", "s1")
        self.mgr.on_change("cb", lambda e, d: None)
        self.mgr.reset()
        self.assertEqual(self.mgr.get_scope_count(), 0)
        self.assertEqual(self.mgr.get_stats()["callbacks"], 0)

    def test_unique_ids(self):
        id1 = self.mgr.create_scope("a1", "s")
        id2 = self.mgr.create_scope("a1", "s")
        self.assertNotEqual(id1, id2)

    def test_prune_excess(self):
        for i in range(10010):
            self.mgr.create_scope("a1", f"scope_{i}")
        self.assertLessEqual(self.mgr.get_scope_count(), 10000)


if __name__ == "__main__":
    unittest.main()
