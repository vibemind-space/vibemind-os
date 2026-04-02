"""Tests for AgentWorkflowLimiter."""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_workflow_limiter import AgentWorkflowLimiter


class TestAgentWorkflowLimiter(unittest.TestCase):
    """Tests for AgentWorkflowLimiter."""

    def setUp(self):
        self.s = AgentWorkflowLimiter()

    # ------------------------------------------------------------------
    # Prefix and constants
    # ------------------------------------------------------------------

    def test_prefix_constant(self):
        self.assertEqual(AgentWorkflowLimiter.PREFIX, "awlm-")

    def test_max_entries_constant(self):
        self.assertEqual(AgentWorkflowLimiter.MAX_ENTRIES, 10000)

    def test_id_has_prefix(self):
        rid = self.s.limit_workflow("a1", "wf1")
        self.assertTrue(rid.startswith("awlm-"))
        self.assertGreater(len(rid), len("awlm-"))

    # ------------------------------------------------------------------
    # Uniqueness
    # ------------------------------------------------------------------

    def test_unique_ids(self):
        ids = set()
        for _ in range(100):
            ids.add(self.s.limit_workflow("a1", "wf1"))
        self.assertEqual(len(ids), 100)

    # ------------------------------------------------------------------
    # Stores fields
    # ------------------------------------------------------------------

    def test_stores_agent_and_workflow(self):
        rid = self.s.limit_workflow("agent-x", "deploy")
        entry = self.s.get_limit(rid)
        self.assertEqual(entry["agent_id"], "agent-x")
        self.assertEqual(entry["workflow_name"], "deploy")

    def test_stores_max_rate(self):
        rid = self.s.limit_workflow("a1", "wf1", max_rate=42)
        entry = self.s.get_limit(rid)
        self.assertEqual(entry["max_rate"], 42)

    def test_stores_default_max_rate(self):
        rid = self.s.limit_workflow("a1", "wf1")
        entry = self.s.get_limit(rid)
        self.assertEqual(entry["max_rate"], 10)

    def test_stores_record_id_in_entry(self):
        rid = self.s.limit_workflow("a1", "wf1")
        entry = self.s.get_limit(rid)
        self.assertEqual(entry["record_id"], rid)

    # ------------------------------------------------------------------
    # Metadata deepcopy
    # ------------------------------------------------------------------

    def test_metadata_deepcopy(self):
        meta = {"key": [1, 2, 3]}
        rid = self.s.limit_workflow("a1", "wf1", metadata=meta)
        meta["key"].append(4)
        entry = self.s.get_limit(rid)
        self.assertEqual(entry["metadata"]["key"], [1, 2, 3])

    def test_metadata_defaults_to_empty_dict(self):
        rid = self.s.limit_workflow("a1", "wf1")
        entry = self.s.get_limit(rid)
        self.assertEqual(entry["metadata"], {})

    # ------------------------------------------------------------------
    # created_at
    # ------------------------------------------------------------------

    def test_created_at_set(self):
        before = time.time()
        rid = self.s.limit_workflow("a1", "wf1")
        after = time.time()
        entry = self.s.get_limit(rid)
        self.assertGreaterEqual(entry["created_at"], before)
        self.assertLessEqual(entry["created_at"], after)

    # ------------------------------------------------------------------
    # Empty agent/workflow returns ""
    # ------------------------------------------------------------------

    def test_empty_agent_id_returns_empty(self):
        rid = self.s.limit_workflow("", "wf1")
        self.assertEqual(rid, "")

    def test_empty_workflow_name_returns_empty(self):
        rid = self.s.limit_workflow("a1", "")
        self.assertEqual(rid, "")

    def test_both_empty_returns_empty(self):
        rid = self.s.limit_workflow("", "")
        self.assertEqual(rid, "")

    # ------------------------------------------------------------------
    # get_limit found / not found / copy
    # ------------------------------------------------------------------

    def test_get_limit_found(self):
        rid = self.s.limit_workflow("a1", "wf1")
        entry = self.s.get_limit(rid)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["agent_id"], "a1")

    def test_get_limit_not_found(self):
        self.assertIsNone(self.s.get_limit("awlm-nonexistent"))

    def test_get_limit_returns_copy(self):
        rid = self.s.limit_workflow("a1", "wf1")
        e1 = self.s.get_limit(rid)
        e1["agent_id"] = "mutated"
        e2 = self.s.get_limit(rid)
        self.assertEqual(e2["agent_id"], "a1")

    # ------------------------------------------------------------------
    # get_limits: all / filter / newest first / limit
    # ------------------------------------------------------------------

    def test_get_limits_all(self):
        self.s.limit_workflow("a1", "wf1")
        self.s.limit_workflow("a2", "wf2")
        results = self.s.get_limits()
        self.assertEqual(len(results), 2)

    def test_get_limits_filter_by_agent(self):
        self.s.limit_workflow("a1", "wf1")
        self.s.limit_workflow("a2", "wf1")
        self.s.limit_workflow("a1", "wf2")
        results = self.s.get_limits(agent_id="a1")
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r["agent_id"] == "a1" for r in results))

    def test_get_limits_newest_first(self):
        rid1 = self.s.limit_workflow("a1", "wf1")
        self.s._state.entries[rid1]["created_at"] = 1000.0
        self.s._state.entries[rid1]["_seq"] = 0
        rid2 = self.s.limit_workflow("a1", "wf2")
        self.s._state.entries[rid2]["created_at"] = 2000.0
        self.s._state.entries[rid2]["_seq"] = 1
        rid3 = self.s.limit_workflow("a1", "wf3")
        self.s._state.entries[rid3]["created_at"] = 3000.0
        self.s._state.entries[rid3]["_seq"] = 2
        results = self.s.get_limits()
        self.assertEqual(results[0]["record_id"], rid3)
        self.assertEqual(results[2]["record_id"], rid1)

    def test_get_limits_limit_param(self):
        for i in range(10):
            self.s.limit_workflow("a1", f"wf{i}")
        results = self.s.get_limits(limit=3)
        self.assertEqual(len(results), 3)

    # ------------------------------------------------------------------
    # get_limit_count: total / filtered / empty
    # ------------------------------------------------------------------

    def test_get_limit_count_total(self):
        self.s.limit_workflow("a1", "wf1")
        self.s.limit_workflow("a2", "wf1")
        self.assertEqual(self.s.get_limit_count(), 2)

    def test_get_limit_count_filtered(self):
        self.s.limit_workflow("a1", "wf1")
        self.s.limit_workflow("a2", "wf1")
        self.s.limit_workflow("a1", "wf2")
        self.assertEqual(self.s.get_limit_count(agent_id="a1"), 2)
        self.assertEqual(self.s.get_limit_count(agent_id="a2"), 1)

    def test_get_limit_count_empty(self):
        self.assertEqual(self.s.get_limit_count(), 0)

    # ------------------------------------------------------------------
    # get_stats: empty / with data
    # ------------------------------------------------------------------

    def test_get_stats_empty(self):
        stats = self.s.get_stats()
        self.assertEqual(stats["total_limits"], 0)
        self.assertEqual(stats["unique_agents"], 0)

    def test_get_stats_with_data(self):
        self.s.limit_workflow("a1", "wf1")
        self.s.limit_workflow("a1", "wf2")
        self.s.limit_workflow("a2", "wf1")
        stats = self.s.get_stats()
        self.assertEqual(stats["total_limits"], 3)
        self.assertEqual(stats["unique_agents"], 2)

    # ------------------------------------------------------------------
    # Callbacks: on_change / remove true / false
    # ------------------------------------------------------------------

    def test_on_change_property_default_none(self):
        self.assertIsNone(self.s.on_change)

    def test_on_change_setter(self):
        handler = lambda a, d: None
        self.s.on_change = handler
        self.assertIs(self.s.on_change, handler)

    def test_on_change_fires_on_limit(self):
        events = []
        self.s.on_change = lambda action, data: events.append((action, data))
        self.s.limit_workflow("a1", "wf1")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "limited")

    def test_callback_fires_events(self):
        events = []
        self.s._state.callbacks["cb1"] = lambda action, data: events.append(action)
        self.s.limit_workflow("a1", "wf1")
        self.assertIn("limited", events)

    def test_remove_callback_true(self):
        self.s._state.callbacks["cb1"] = lambda a, d: None
        self.assertTrue(self.s.remove_callback("cb1"))

    def test_remove_callback_false(self):
        self.assertFalse(self.s.remove_callback("nonexistent"))

    def test_callback_exception_silent(self):
        def bad_cb(a, d):
            raise RuntimeError("boom")
        self.s._state.callbacks["bad"] = bad_cb
        rid = self.s.limit_workflow("a1", "wf1")
        self.assertIsNotNone(self.s.get_limit(rid))

    def test_on_change_exception_silent(self):
        def bad_handler(a, d):
            raise RuntimeError("boom")
        self.s.on_change = bad_handler
        rid = self.s.limit_workflow("a1", "wf1")
        self.assertIsNotNone(self.s.get_limit(rid))

    # ------------------------------------------------------------------
    # Prune: MAX=5, add 8, count < 8
    # ------------------------------------------------------------------

    def test_prune_removes_oldest(self):
        self.s.MAX_ENTRIES = 5
        for i in range(8):
            self.s.limit_workflow(f"a{i}", f"wf{i}")
        self.assertLess(self.s.get_limit_count(), 8)

    # ------------------------------------------------------------------
    # Reset: clears / callbacks / seq
    # ------------------------------------------------------------------

    def test_reset_clears_entries(self):
        self.s.limit_workflow("a1", "wf1")
        self.s.reset()
        self.assertEqual(self.s.get_limit_count(), 0)

    def test_reset_clears_callbacks(self):
        self.s._state.callbacks["cb1"] = lambda a, d: None
        self.s.on_change = lambda a, d: None
        self.s.reset()
        self.assertEqual(len(self.s._state.callbacks), 0)
        self.assertIsNone(self.s.on_change)

    def test_reset_resets_seq(self):
        self.s.limit_workflow("a1", "wf1")
        self.assertGreater(self.s._state._seq, 0)
        self.s.reset()
        self.assertEqual(self.s._state._seq, 0)


if __name__ == "__main__":
    unittest.main()
