"""Tests for PipelineStepBalancer service."""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_step_balancer import PipelineStepBalancer


class TestPipelineStepBalancer(unittest.TestCase):
    """Tests for PipelineStepBalancer."""

    def setUp(self):
        self.svc = PipelineStepBalancer()

    # -- balance -----------------------------------------------------------

    def test_balance_returns_id(self):
        rid = self.svc.balance("p1", "step_a")
        self.assertIsInstance(rid, str)
        self.assertTrue(rid.startswith("psbl-"))

    def test_balance_stores_fields(self):
        rid = self.svc.balance(
            "p1", "step_a", load_factor=2.5, strategy="weighted", metadata={"zone": "us-east"}
        )
        entry = self.svc.get_balance(rid)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["pipeline_id"], "p1")
        self.assertEqual(entry["step_name"], "step_a")
        self.assertEqual(entry["load_factor"], 2.5)
        self.assertEqual(entry["strategy"], "weighted")
        self.assertEqual(entry["metadata"], {"zone": "us-east"})
        self.assertIn("created_at", entry)
        self.assertIn("updated_at", entry)

    def test_balance_default_load_factor(self):
        rid = self.svc.balance("p1", "step_a")
        entry = self.svc.get_balance(rid)
        self.assertEqual(entry["load_factor"], 1.0)

    def test_balance_default_strategy(self):
        rid = self.svc.balance("p1", "step_a")
        entry = self.svc.get_balance(rid)
        self.assertEqual(entry["strategy"], "round_robin")

    def test_balance_default_metadata(self):
        rid = self.svc.balance("p1", "step_a")
        entry = self.svc.get_balance(rid)
        self.assertEqual(entry["metadata"], {})

    def test_balance_custom_load_factor(self):
        rid = self.svc.balance("p1", "step_a", load_factor=5.0)
        entry = self.svc.get_balance(rid)
        self.assertEqual(entry["load_factor"], 5.0)

    def test_balance_custom_strategy(self):
        rid = self.svc.balance("p1", "step_a", strategy="least_connections")
        entry = self.svc.get_balance(rid)
        self.assertEqual(entry["strategy"], "least_connections")

    def test_balance_unique_ids(self):
        rid1 = self.svc.balance("p1", "step_a")
        rid2 = self.svc.balance("p1", "step_a")
        self.assertNotEqual(rid1, rid2)

    def test_balance_fires_callback(self):
        events = []
        self.svc.on_change = lambda action, data: events.append((action, data))
        self.svc.balance("p1", "step_a", load_factor=2.0)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "balanced")
        self.assertEqual(events[0][1]["load_factor"], 2.0)

    def test_balance_entry_has_seq(self):
        rid = self.svc.balance("p1", "step_a")
        entry = self.svc.get_balance(rid)
        self.assertIn("_seq", entry)
        self.assertIsInstance(entry["_seq"], int)

    # -- get_balance -------------------------------------------------------

    def test_get_balance_not_found(self):
        result = self.svc.get_balance("nonexistent")
        self.assertIsNone(result)

    def test_get_balance_returns_copy(self):
        rid = self.svc.balance("p1", "step_a")
        entry = self.svc.get_balance(rid)
        entry["pipeline_id"] = "modified"
        original = self.svc.get_balance(rid)
        self.assertEqual(original["pipeline_id"], "p1")

    # -- get_balances ------------------------------------------------------

    def test_get_balances_empty(self):
        result = self.svc.get_balances()
        self.assertEqual(result, [])

    def test_get_balances_newest_first(self):
        rid1 = self.svc.balance("p1", "step_a")
        rid2 = self.svc.balance("p1", "step_b")
        rid3 = self.svc.balance("p1", "step_c")
        result = self.svc.get_balances()
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["record_id"], rid3)
        self.assertEqual(result[1]["record_id"], rid2)
        self.assertEqual(result[2]["record_id"], rid1)

    def test_get_balances_filter_by_pipeline(self):
        self.svc.balance("p1", "step_a")
        self.svc.balance("p2", "step_b")
        self.svc.balance("p1", "step_c")
        result = self.svc.get_balances(pipeline_id="p1")
        self.assertEqual(len(result), 2)
        for entry in result:
            self.assertEqual(entry["pipeline_id"], "p1")

    def test_get_balances_limit(self):
        for i in range(10):
            self.svc.balance("p1", f"step_{i}")
        result = self.svc.get_balances(limit=3)
        self.assertEqual(len(result), 3)

    def test_get_balances_returns_copies(self):
        self.svc.balance("p1", "step_a")
        result = self.svc.get_balances()
        result[0]["pipeline_id"] = "modified"
        original = self.svc.get_balances()
        self.assertEqual(original[0]["pipeline_id"], "p1")

    def test_get_balances_filter_nonexistent_pipeline(self):
        self.svc.balance("p1", "step_a")
        result = self.svc.get_balances(pipeline_id="nope")
        self.assertEqual(result, [])

    def test_get_balances_default_limit_is_50(self):
        for i in range(60):
            self.svc.balance("p1", f"step_{i}")
        result = self.svc.get_balances()
        self.assertEqual(len(result), 50)

    # -- get_balance_count -------------------------------------------------

    def test_get_balance_count_empty(self):
        self.assertEqual(self.svc.get_balance_count(), 0)

    def test_get_balance_count_total(self):
        self.svc.balance("p1", "step_a")
        self.svc.balance("p2", "step_b")
        self.assertEqual(self.svc.get_balance_count(), 2)

    def test_get_balance_count_by_pipeline(self):
        self.svc.balance("p1", "step_a")
        self.svc.balance("p2", "step_b")
        self.svc.balance("p1", "step_c")
        self.assertEqual(self.svc.get_balance_count(pipeline_id="p1"), 2)
        self.assertEqual(self.svc.get_balance_count(pipeline_id="p2"), 1)

    def test_get_balance_count_nonexistent_pipeline(self):
        self.svc.balance("p1", "step_a")
        self.assertEqual(self.svc.get_balance_count(pipeline_id="nope"), 0)

    # -- callbacks ---------------------------------------------------------

    def test_on_change_property_default_none(self):
        self.assertIsNone(self.svc.on_change)

    def test_on_change_set_and_get(self):
        cb = lambda a, d: None
        self.svc.on_change = cb
        self.assertIs(self.svc.on_change, cb)

    def test_on_change_clear(self):
        self.svc.on_change = lambda a, d: None
        self.svc.on_change = None
        self.assertIsNone(self.svc.on_change)

    def test_remove_callback_exists(self):
        self.svc.on_change = lambda a, d: None
        self.assertTrue(self.svc.remove_callback("_on_change"))
        self.assertIsNone(self.svc.on_change)

    def test_remove_callback_missing(self):
        self.assertFalse(self.svc.remove_callback("nonexistent"))

    def test_callback_exception_does_not_propagate(self):
        def bad_cb(action, data):
            raise RuntimeError("boom")
        self.svc.on_change = bad_cb
        # Should not raise
        rid = self.svc.balance("p1", "step_a")
        self.assertIsNotNone(rid)

    def test_multiple_callbacks_all_fire(self):
        events = []
        self.svc.on_change = lambda action, data: events.append("on_change")
        self.svc._state._callbacks["extra"] = lambda action, data: events.append("extra")
        self.svc.balance("p1", "step_a")
        self.assertIn("on_change", events)
        self.assertIn("extra", events)

    # -- get_stats ---------------------------------------------------------

    def test_get_stats_empty(self):
        stats = self.svc.get_stats()
        self.assertEqual(stats["total_balances"], 0)

    def test_get_stats_with_data(self):
        self.svc.balance("p1", "step_a", strategy="round_robin")
        self.svc.balance("p2", "step_b", strategy="weighted")
        self.svc.balance("p1", "step_c", strategy="round_robin")
        stats = self.svc.get_stats()
        self.assertEqual(stats["total_balances"], 3)
        self.assertEqual(stats["unique_pipelines"], 2)
        self.assertEqual(stats["unique_steps"], 3)
        self.assertEqual(stats["unique_strategies"], 2)

    # -- reset -------------------------------------------------------------

    def test_reset_clears_entries(self):
        self.svc.balance("p1", "step_a")
        self.svc.reset()
        self.assertEqual(self.svc.get_balance_count(), 0)

    def test_reset_clears_callbacks(self):
        self.svc.on_change = lambda a, d: None
        self.svc.reset()
        self.assertIsNone(self.svc.on_change)

    def test_reset_resets_sequence(self):
        self.svc.balance("p1", "step_a")
        self.svc.reset()
        rid = self.svc.balance("p1", "step_a")
        self.assertTrue(rid.startswith("psbl-"))

    # -- pruning -----------------------------------------------------------

    def test_prune_removes_oldest_quarter(self):
        self.svc.MAX_ENTRIES = 10
        for i in range(12):
            self.svc.balance("p1", f"step_{i}")
        count = self.svc.get_balance_count()
        self.assertLessEqual(count, 11)

    # -- PREFIX / MAX_ENTRIES ----------------------------------------------

    def test_prefix_value(self):
        self.assertEqual(PipelineStepBalancer.PREFIX, "psbl-")

    def test_max_entries_value(self):
        self.assertEqual(PipelineStepBalancer.MAX_ENTRIES, 10000)


if __name__ == "__main__":
    unittest.main()
