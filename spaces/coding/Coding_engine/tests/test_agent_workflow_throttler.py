"""Tests for AgentWorkflowThrottler."""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_workflow_throttler import AgentWorkflowThrottler


class TestAgentWorkflowThrottler(unittest.TestCase):
    """Tests for AgentWorkflowThrottler."""

    def setUp(self):
        self.svc = AgentWorkflowThrottler()

    # ------------------------------------------------------------------
    # Basic throttle creation
    # ------------------------------------------------------------------

    def test_throttle_returns_id(self):
        rid = self.svc.throttle("a1", "wf1")
        self.assertTrue(rid.startswith("awth-"))
        self.assertGreater(len(rid), len("awth-"))

    def test_throttle_default_allowed(self):
        rid = self.svc.throttle("a1", "wf1")
        entry = self.svc.get_throttle(rid)
        self.assertTrue(entry["allowed"])

    def test_throttle_records_agent_and_workflow(self):
        rid = self.svc.throttle("agent-x", "deploy")
        entry = self.svc.get_throttle(rid)
        self.assertEqual(entry["agent_id"], "agent-x")
        self.assertEqual(entry["workflow_name"], "deploy")

    def test_throttle_default_rate_and_window(self):
        rid = self.svc.throttle("a1", "wf1")
        entry = self.svc.get_throttle(rid)
        self.assertEqual(entry["max_rate"], 10)
        self.assertEqual(entry["window_seconds"], 60)

    def test_throttle_custom_rate_and_window(self):
        rid = self.svc.throttle("a1", "wf1", max_rate=5, window_seconds=30)
        entry = self.svc.get_throttle(rid)
        self.assertEqual(entry["max_rate"], 5)
        self.assertEqual(entry["window_seconds"], 30)

    def test_throttle_with_metadata(self):
        meta = {"source": "cli", "priority": "high"}
        rid = self.svc.throttle("a1", "wf1", metadata=meta)
        entry = self.svc.get_throttle(rid)
        self.assertEqual(entry["metadata"], meta)

    def test_throttle_metadata_defaults_to_empty_dict(self):
        rid = self.svc.throttle("a1", "wf1")
        entry = self.svc.get_throttle(rid)
        self.assertEqual(entry["metadata"], {})

    def test_throttle_created_at_set(self):
        before = time.time()
        rid = self.svc.throttle("a1", "wf1")
        after = time.time()
        entry = self.svc.get_throttle(rid)
        self.assertGreaterEqual(entry["created_at"], before)
        self.assertLessEqual(entry["created_at"], after)

    # ------------------------------------------------------------------
    # Rate limiting behaviour
    # ------------------------------------------------------------------

    def test_throttle_denies_when_rate_exceeded(self):
        for _ in range(3):
            self.svc.throttle("a1", "wf1", max_rate=3, window_seconds=60)
        rid = self.svc.throttle("a1", "wf1", max_rate=3, window_seconds=60)
        entry = self.svc.get_throttle(rid)
        self.assertFalse(entry["allowed"])

    def test_throttle_allows_different_agents(self):
        for _ in range(3):
            self.svc.throttle("a1", "wf1", max_rate=3)
        rid = self.svc.throttle("a2", "wf1", max_rate=3)
        entry = self.svc.get_throttle(rid)
        self.assertTrue(entry["allowed"])

    def test_throttle_allows_different_workflows(self):
        for _ in range(3):
            self.svc.throttle("a1", "wf1", max_rate=3)
        rid = self.svc.throttle("a1", "wf2", max_rate=3)
        entry = self.svc.get_throttle(rid)
        self.assertTrue(entry["allowed"])

    def test_throttle_recent_count_increments(self):
        rid1 = self.svc.throttle("a1", "wf1")
        rid2 = self.svc.throttle("a1", "wf1")
        e1 = self.svc.get_throttle(rid1)
        e2 = self.svc.get_throttle(rid2)
        self.assertEqual(e1["recent_count"], 0)
        self.assertEqual(e2["recent_count"], 1)

    def test_throttle_window_expiry(self):
        # Create entries with artificially old timestamps
        rid1 = self.svc.throttle("a1", "wf1", max_rate=1, window_seconds=60)
        self.svc._state.entries[rid1]["created_at"] = time.time() - 120
        rid2 = self.svc.throttle("a1", "wf1", max_rate=1, window_seconds=60)
        entry = self.svc.get_throttle(rid2)
        self.assertTrue(entry["allowed"])

    # ------------------------------------------------------------------
    # get_throttle
    # ------------------------------------------------------------------

    def test_get_throttle_not_found(self):
        self.assertIsNone(self.svc.get_throttle("awth-nonexistent"))

    def test_get_throttle_returns_copy(self):
        rid = self.svc.throttle("a1", "wf1")
        e1 = self.svc.get_throttle(rid)
        e2 = self.svc.get_throttle(rid)
        self.assertEqual(e1, e2)
        e1["agent_id"] = "mutated"
        self.assertNotEqual(self.svc.get_throttle(rid)["agent_id"], "mutated")

    # ------------------------------------------------------------------
    # get_throttles
    # ------------------------------------------------------------------

    def test_get_throttles_returns_all(self):
        self.svc.throttle("a1", "wf1")
        self.svc.throttle("a2", "wf2")
        results = self.svc.get_throttles()
        self.assertEqual(len(results), 2)

    def test_get_throttles_filter_by_agent(self):
        self.svc.throttle("a1", "wf1")
        self.svc.throttle("a2", "wf1")
        self.svc.throttle("a1", "wf2")
        results = self.svc.get_throttles(agent_id="a1")
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r["agent_id"] == "a1" for r in results))

    def test_get_throttles_newest_first(self):
        rid1 = self.svc.throttle("a1", "wf1")
        self.svc._state.entries[rid1]["created_at"] = 1000.0
        self.svc._state.entries[rid1]["_seq"] = 0
        rid2 = self.svc.throttle("a1", "wf2")
        self.svc._state.entries[rid2]["created_at"] = 2000.0
        self.svc._state.entries[rid2]["_seq"] = 1
        rid3 = self.svc.throttle("a1", "wf3")
        self.svc._state.entries[rid3]["created_at"] = 3000.0
        self.svc._state.entries[rid3]["_seq"] = 2
        results = self.svc.get_throttles()
        self.assertEqual(results[0]["record_id"], rid3)
        self.assertEqual(results[2]["record_id"], rid1)

    def test_get_throttles_limit(self):
        for i in range(10):
            self.svc.throttle("a1", f"wf{i}")
        results = self.svc.get_throttles(limit=3)
        self.assertEqual(len(results), 3)

    # ------------------------------------------------------------------
    # get_throttle_count
    # ------------------------------------------------------------------

    def test_get_throttle_count_all(self):
        self.svc.throttle("a1", "wf1")
        self.svc.throttle("a2", "wf1")
        self.assertEqual(self.svc.get_throttle_count(), 2)

    def test_get_throttle_count_by_agent(self):
        self.svc.throttle("a1", "wf1")
        self.svc.throttle("a2", "wf1")
        self.svc.throttle("a1", "wf2")
        self.assertEqual(self.svc.get_throttle_count(agent_id="a1"), 2)
        self.assertEqual(self.svc.get_throttle_count(agent_id="a2"), 1)

    # ------------------------------------------------------------------
    # get_stats
    # ------------------------------------------------------------------

    def test_get_stats_empty(self):
        stats = self.svc.get_stats()
        self.assertEqual(stats["total_records"], 0)
        self.assertEqual(stats["allowed_count"], 0)
        self.assertEqual(stats["denied_count"], 0)
        self.assertEqual(stats["unique_agents"], 0)

    def test_get_stats_with_data(self):
        for _ in range(3):
            self.svc.throttle("a1", "wf1", max_rate=2)
        self.svc.throttle("a2", "wf1")
        stats = self.svc.get_stats()
        self.assertEqual(stats["total_records"], 4)
        self.assertEqual(stats["allowed_count"], 3)
        self.assertEqual(stats["denied_count"], 1)
        self.assertEqual(stats["unique_agents"], 2)

    # ------------------------------------------------------------------
    # reset
    # ------------------------------------------------------------------

    def test_reset_clears_entries(self):
        self.svc.throttle("a1", "wf1")
        self.svc.on_change = lambda a, d: None
        self.svc.reset()
        self.assertEqual(self.svc.get_throttle_count(), 0)
        self.assertEqual(self.svc.get_stats()["total_records"], 0)
        self.assertIsNone(self.svc.on_change)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def test_on_change_property(self):
        self.assertIsNone(self.svc.on_change)
        handler = lambda a, d: None
        self.svc.on_change = handler
        self.assertIs(self.svc.on_change, handler)

    def test_on_change_fires_on_throttle(self):
        events = []
        self.svc.on_change = lambda action, data: events.append((action, data))
        self.svc.throttle("a1", "wf1")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "throttle_checked")
        self.assertIn("allowed", events[0][1])

    def test_callback_fires_events(self):
        events = []
        self.svc._callbacks["test"] = lambda action, data: events.append(action)
        self.svc.throttle("a1", "wf1")
        self.assertIn("throttle_checked", events)

    def test_remove_callback(self):
        self.svc._callbacks["cb1"] = lambda a, d: None
        self.assertTrue(self.svc.remove_callback("cb1"))
        self.assertFalse(self.svc.remove_callback("cb1"))

    def test_callback_exception_silent(self):
        def bad_cb(a, d):
            raise RuntimeError("boom")
        self.svc._callbacks["bad"] = bad_cb
        rid = self.svc.throttle("a1", "wf1")
        self.assertIsNotNone(self.svc.get_throttle(rid))

    def test_on_change_exception_silent(self):
        def bad_handler(a, d):
            raise RuntimeError("boom")
        self.svc.on_change = bad_handler
        rid = self.svc.throttle("a1", "wf1")
        self.assertIsNotNone(self.svc.get_throttle(rid))

    # ------------------------------------------------------------------
    # ID uniqueness and constants
    # ------------------------------------------------------------------

    def test_unique_ids(self):
        ids = set()
        for _ in range(100):
            ids.add(self.svc.throttle("a1", "wf1", max_rate=1000))
        self.assertEqual(len(ids), 100)

    def test_prefix_constant(self):
        self.assertEqual(AgentWorkflowThrottler.PREFIX, "awth-")

    def test_max_entries_constant(self):
        self.assertEqual(AgentWorkflowThrottler.MAX_ENTRIES, 10000)

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def test_pruning(self):
        self.svc.MAX_ENTRIES = 10
        for i in range(15):
            self.svc.throttle(f"a{i}", f"wf{i}", max_rate=1000)
        self.assertLessEqual(len(self.svc._state.entries), 13)


if __name__ == "__main__":
    unittest.main()
