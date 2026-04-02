from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import unittest
from src.services.agent_task_reviewer import AgentTaskReviewer


class TestAgentTaskReviewer(unittest.TestCase):

    def setUp(self):
        self.s = AgentTaskReviewer()

    # -- basic review --
    def test_review_returns_id_with_prefix(self):
        rid = self.s.review("t1", "a1")
        self.assertTrue(rid.startswith("atrv-"))

    def test_review_fields_correct(self):
        rid = self.s.review("t1", "a1", verdict="approved", metadata={"k": "v"})
        rec = self.s.get_review(rid)
        self.assertEqual(rec["task_id"], "t1")
        self.assertEqual(rec["agent_id"], "a1")
        self.assertEqual(rec["verdict"], "approved")
        self.assertEqual(rec["metadata"], {"k": "v"})
        self.assertIn("created_at", rec)
        self.assertEqual(rec["record_id"], rid)

    def test_default_verdict_pending(self):
        rid = self.s.review("t1", "a1")
        rec = self.s.get_review(rid)
        self.assertEqual(rec["verdict"], "pending")

    def test_metadata_deepcopy(self):
        meta = {"nested": [1, 2]}
        rid = self.s.review("t1", "a1", metadata=meta)
        meta["nested"].append(3)
        rec = self.s.get_review(rid)
        self.assertEqual(rec["metadata"]["nested"], [1, 2])

    # -- empty task_id / agent_id --
    def test_empty_task_id_returns_empty(self):
        self.assertEqual(self.s.review("", "a1"), "")

    def test_empty_agent_id_returns_empty(self):
        self.assertEqual(self.s.review("t1", ""), "")

    # -- get_review --
    def test_get_review_found(self):
        rid = self.s.review("t1", "a1")
        self.assertIsNotNone(self.s.get_review(rid))

    def test_get_review_not_found(self):
        self.assertIsNone(self.s.get_review("nonexistent"))

    def test_get_review_returns_copy(self):
        rid = self.s.review("t1", "a1")
        r1 = self.s.get_review(rid)
        r2 = self.s.get_review(rid)
        self.assertEqual(r1, r2)
        self.assertIsNot(r1, r2)

    # -- get_reviews --
    def test_get_reviews_all(self):
        self.s.review("t1", "a1")
        self.s.review("t2", "a2")
        self.assertEqual(len(self.s.get_reviews()), 2)

    def test_get_reviews_filter_by_agent(self):
        self.s.review("t1", "a1")
        self.s.review("t2", "a2")
        self.s.review("t3", "a1")
        results = self.s.get_reviews(agent_id="a1")
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r["agent_id"], "a1")

    def test_get_reviews_newest_first(self):
        r1 = self.s.review("t1", "a1")
        r2 = self.s.review("t2", "a1")
        reviews = self.s.get_reviews()
        self.assertEqual(reviews[0]["record_id"], r2)
        self.assertEqual(reviews[1]["record_id"], r1)

    # -- get_review_count --
    def test_get_review_count_total(self):
        self.s.review("t1", "a1")
        self.s.review("t2", "a2")
        self.assertEqual(self.s.get_review_count(), 2)

    def test_get_review_count_filtered(self):
        self.s.review("t1", "a1")
        self.s.review("t2", "a2")
        self.s.review("t3", "a1")
        self.assertEqual(self.s.get_review_count(agent_id="a1"), 2)

    # -- get_stats --
    def test_get_stats(self):
        self.s.review("t1", "a1")
        self.s.review("t2", "a2")
        self.s.review("t3", "a1")
        stats = self.s.get_stats()
        self.assertEqual(stats["total_reviews"], 3)
        self.assertEqual(stats["unique_agents"], 2)

    # -- on_change callback --
    def test_on_change_callback_fires(self):
        calls = []
        self.s.on_change = lambda action, **kw: calls.append(action)
        self.s.review("t1", "a1")
        self.assertEqual(calls, ["review"])

    # -- remove_callback --
    def test_remove_callback_true(self):
        self.s._state.callbacks["cb1"] = lambda action, **kw: None
        self.assertTrue(self.s.remove_callback("cb1"))
        self.assertNotIn("cb1", self.s._state.callbacks)

    def test_remove_callback_false(self):
        self.assertFalse(self.s.remove_callback("nonexistent"))

    # -- prune --
    def test_prune_removes_oldest_quarter(self):
        self.s.MAX_ENTRIES = 5
        for i in range(7):
            self.s.review(f"t{i}", f"a{i}")
        # After adding 6th entry (index 5), prune triggers: 6 > 5, removes 6//4=1
        # After adding 7th entry, prune triggers again
        self.assertLessEqual(len(self.s._state.entries), 7)
        # Verify count is reduced from what it would be without pruning
        self.assertLessEqual(self.s.get_review_count(), 6)

    # -- reset --
    def test_reset_clears_state(self):
        self.s.review("t1", "a1")
        self.s.on_change = lambda action, **kw: None
        self.s.reset()
        self.assertEqual(self.s.get_review_count(), 0)
        self.assertEqual(len(self.s._state.entries), 0)
        self.assertIsNone(self.s.on_change)


if __name__ == "__main__":
    unittest.main()
