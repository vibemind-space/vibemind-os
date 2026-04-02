"""Tests for agent_task_budget service."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.agent_task_budget import AgentTaskBudget


class TestAgentTaskBudget(unittest.TestCase):
    def setUp(self):
        self.svc = AgentTaskBudget()

    def test_create_budget_returns_id(self):
        bid = self.svc.create_budget("t1", "a1")
        self.assertTrue(bid.startswith("atbu-"))

    def test_create_budget_default_values(self):
        bid = self.svc.create_budget("t1", "a1")
        budget = self.svc.get_budget(bid)
        self.assertEqual(budget["limit"], 100.0)
        self.assertEqual(budget["unit"], "credits")
        self.assertEqual(budget["spent"], 0.0)
        self.assertEqual(budget["remaining"], 100.0)

    def test_create_budget_custom_values(self):
        bid = self.svc.create_budget("t1", "a1", limit=500.0, unit="tokens")
        budget = self.svc.get_budget(bid)
        self.assertEqual(budget["limit"], 500.0)
        self.assertEqual(budget["unit"], "tokens")

    def test_spend_success(self):
        bid = self.svc.create_budget("t1", "a1", limit=50.0)
        result = self.svc.spend(bid, 20.0, "test spend")
        self.assertTrue(result)
        self.assertAlmostEqual(self.svc.get_remaining(bid), 30.0)

    def test_spend_insufficient_funds(self):
        bid = self.svc.create_budget("t1", "a1", limit=10.0)
        result = self.svc.spend(bid, 20.0)
        self.assertFalse(result)
        self.assertAlmostEqual(self.svc.get_remaining(bid), 10.0)

    def test_spend_nonexistent_budget(self):
        result = self.svc.spend("atbu-fake", 5.0)
        self.assertFalse(result)

    def test_spend_exact_amount(self):
        bid = self.svc.create_budget("t1", "a1", limit=25.0)
        result = self.svc.spend(bid, 25.0)
        self.assertTrue(result)
        self.assertAlmostEqual(self.svc.get_remaining(bid), 0.0)

    def test_spend_records_transactions(self):
        bid = self.svc.create_budget("t1", "a1")
        self.svc.spend(bid, 10.0, "first")
        self.svc.spend(bid, 5.0, "second")
        budget = self.svc.get_budget(bid)
        self.assertEqual(len(budget["transactions"]), 2)
        self.assertEqual(budget["transactions"][0]["description"], "first")
        self.assertEqual(budget["transactions"][1]["amount"], 5.0)

    def test_get_budget_not_found(self):
        self.assertIsNone(self.svc.get_budget("atbu-missing"))

    def test_get_remaining_not_found(self):
        self.assertEqual(self.svc.get_remaining("atbu-nope"), -1)

    def test_get_budgets_all(self):
        self.svc.create_budget("t1", "a1")
        self.svc.create_budget("t2", "a2")
        results = self.svc.get_budgets()
        self.assertEqual(len(results), 2)

    def test_get_budgets_filter_by_agent(self):
        self.svc.create_budget("t1", "a1")
        self.svc.create_budget("t2", "a1")
        self.svc.create_budget("t3", "a2")
        results = self.svc.get_budgets(agent_id="a1")
        self.assertEqual(len(results), 2)

    def test_get_budgets_filter_by_task(self):
        self.svc.create_budget("t1", "a1")
        self.svc.create_budget("t1", "a2")
        self.svc.create_budget("t2", "a1")
        results = self.svc.get_budgets(task_id="t1")
        self.assertEqual(len(results), 2)

    def test_get_budgets_newest_first(self):
        b1 = self.svc.create_budget("t1", "a1")
        # Ensure distinct timestamps
        import time
        time.sleep(0.01)
        b2 = self.svc.create_budget("t2", "a1")
        results = self.svc.get_budgets()
        self.assertEqual(results[0]["budget_id"], b2)

    def test_get_budgets_limit(self):
        for i in range(5):
            self.svc.create_budget(f"t{i}", "a1")
        results = self.svc.get_budgets(limit=3)
        self.assertEqual(len(results), 3)

    def test_get_budget_count_all(self):
        self.svc.create_budget("t1", "a1")
        self.svc.create_budget("t2", "a2")
        self.assertEqual(self.svc.get_budget_count(), 2)

    def test_get_budget_count_by_agent(self):
        self.svc.create_budget("t1", "a1")
        self.svc.create_budget("t2", "a1")
        self.svc.create_budget("t3", "a2")
        self.assertEqual(self.svc.get_budget_count(agent_id="a1"), 2)

    def test_get_stats(self):
        b1 = self.svc.create_budget("t1", "a1", limit=100.0)
        b2 = self.svc.create_budget("t2", "a2", limit=200.0)
        self.svc.spend(b1, 30.0)
        self.svc.spend(b2, 50.0)
        stats = self.svc.get_stats()
        self.assertEqual(stats["total_budgets"], 2)
        self.assertAlmostEqual(stats["total_spent"], 80.0)
        self.assertAlmostEqual(stats["total_remaining"], 220.0)

    def test_reset(self):
        self.svc.create_budget("t1", "a1")
        self.svc.reset()
        self.assertEqual(self.svc.get_budget_count(), 0)
        self.assertEqual(self.svc.get_stats()["total_budgets"], 0)

    def test_on_change_property(self):
        events = []
        self.svc.on_change = lambda action, data: events.append(action)
        self.svc.create_budget("t1", "a1")
        self.assertIn("budget_created", events)

    def test_register_and_remove_callback(self):
        events = []
        self.svc.register_callback("cb1", lambda a, d: events.append(a))
        self.svc.create_budget("t1", "a1")
        self.assertIn("budget_created", events)
        removed = self.svc.remove_callback("cb1")
        self.assertTrue(removed)
        removed2 = self.svc.remove_callback("cb1")
        self.assertFalse(removed2)

    def test_fire_silent_exception(self):
        def bad_cb(action, data):
            raise RuntimeError("boom")
        self.svc.on_change = bad_cb
        # Should not raise
        bid = self.svc.create_budget("t1", "a1")
        self.assertIsNotNone(bid)

    def test_unique_ids(self):
        ids = set()
        for i in range(20):
            ids.add(self.svc.create_budget(f"t{i}", "a1"))
        self.assertEqual(len(ids), 20)

    def test_multiple_spends(self):
        bid = self.svc.create_budget("t1", "a1", limit=100.0)
        self.svc.spend(bid, 30.0)
        self.svc.spend(bid, 25.0)
        self.svc.spend(bid, 20.0)
        self.assertAlmostEqual(self.svc.get_remaining(bid), 25.0)
        # Next spend should fail if over
        result = self.svc.spend(bid, 30.0)
        self.assertFalse(result)
        self.assertAlmostEqual(self.svc.get_remaining(bid), 25.0)


if __name__ == "__main__":
    unittest.main()
