"""Tests for PipelineStepOptimizer service."""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_step_optimizer import PipelineStepOptimizer


class TestPipelineStepOptimizer(unittest.TestCase):
    """Tests for PipelineStepOptimizer."""

    def setUp(self):
        self.svc = PipelineStepOptimizer()

    # -- optimize --------------------------------------------------------

    def test_optimize_returns_id(self):
        rid = self.svc.optimize("p1", "step_a")
        self.assertIsInstance(rid, str)
        self.assertTrue(rid.startswith("psop-"))

    def test_optimize_stores_fields(self):
        rid = self.svc.optimize("p1", "step_a", level="aggressive", metadata={"tag": "v1"})
        entry = self.svc.get_optimization(rid)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["pipeline_id"], "p1")
        self.assertEqual(entry["step_name"], "step_a")
        self.assertEqual(entry["level"], "aggressive")
        self.assertEqual(entry["metadata"], {"tag": "v1"})
        self.assertIn("created_at", entry)
        self.assertIn("updated_at", entry)

    def test_optimize_default_level(self):
        rid = self.svc.optimize("p1", "step_a")
        entry = self.svc.get_optimization(rid)
        self.assertEqual(entry["level"], "standard")

    def test_optimize_empty_pipeline_id(self):
        rid = self.svc.optimize("", "step_a")
        self.assertEqual(rid, "")

    def test_optimize_empty_step_name(self):
        rid = self.svc.optimize("p1", "")
        self.assertEqual(rid, "")

    # -- get_optimization ------------------------------------------------

    def test_get_optimization_not_found(self):
        result = self.svc.get_optimization("nonexistent")
        self.assertIsNone(result)

    def test_get_optimization_returns_copy(self):
        rid = self.svc.optimize("p1", "step_a")
        entry = self.svc.get_optimization(rid)
        entry["pipeline_id"] = "modified"
        original = self.svc.get_optimization(rid)
        self.assertEqual(original["pipeline_id"], "p1")

    # -- get_optimizations -----------------------------------------------

    def test_get_optimizations_empty(self):
        result = self.svc.get_optimizations()
        self.assertEqual(result, [])

    def test_get_optimizations_newest_first(self):
        rid1 = self.svc.optimize("p1", "step_a")
        rid2 = self.svc.optimize("p1", "step_b")
        rid3 = self.svc.optimize("p1", "step_c")
        result = self.svc.get_optimizations()
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["record_id"], rid3)
        self.assertEqual(result[2]["record_id"], rid1)

    def test_get_optimizations_filter_by_pipeline(self):
        self.svc.optimize("p1", "step_a")
        self.svc.optimize("p2", "step_b")
        self.svc.optimize("p1", "step_c")
        result = self.svc.get_optimizations(pipeline_id="p1")
        self.assertEqual(len(result), 2)
        for r in result:
            self.assertEqual(r["pipeline_id"], "p1")

    def test_get_optimizations_limit(self):
        for i in range(10):
            self.svc.optimize("p1", f"step_{i}")
        result = self.svc.get_optimizations(limit=3)
        self.assertEqual(len(result), 3)

    # -- get_optimization_count ------------------------------------------

    def test_get_optimization_count_all(self):
        self.svc.optimize("p1", "step_a")
        self.svc.optimize("p2", "step_b")
        self.assertEqual(self.svc.get_optimization_count(), 2)

    def test_get_optimization_count_by_pipeline(self):
        self.svc.optimize("p1", "step_a")
        self.svc.optimize("p2", "step_b")
        self.svc.optimize("p1", "step_c")
        self.assertEqual(self.svc.get_optimization_count(pipeline_id="p1"), 2)
        self.assertEqual(self.svc.get_optimization_count(pipeline_id="p2"), 1)
        self.assertEqual(self.svc.get_optimization_count(pipeline_id="p3"), 0)

    def test_get_optimization_count_empty(self):
        self.assertEqual(self.svc.get_optimization_count(), 0)

    # -- get_stats -------------------------------------------------------

    def test_get_stats_empty(self):
        stats = self.svc.get_stats()
        self.assertEqual(stats["total_optimizations"], 0)
        self.assertEqual(stats["unique_pipelines"], 0)

    def test_get_stats_with_data(self):
        self.svc.optimize("p1", "step_a")
        self.svc.optimize("p1", "step_b")
        self.svc.optimize("p2", "step_a")
        stats = self.svc.get_stats()
        self.assertEqual(stats["total_optimizations"], 3)
        self.assertEqual(stats["unique_pipelines"], 2)

    # -- reset -----------------------------------------------------------

    def test_reset(self):
        self.svc.optimize("p1", "step_a")
        self.svc.optimize("p2", "step_b")
        self.svc.reset()
        self.assertEqual(self.svc.get_optimization_count(), 0)
        self.assertEqual(self.svc.get_stats()["total_optimizations"], 0)

    def test_reset_clears_callbacks(self):
        self.svc.on_change = lambda a, d: None
        self.svc.reset()
        self.assertIsNone(self.svc.on_change)

    # -- callbacks -------------------------------------------------------

    def test_on_change_fires_on_optimize(self):
        events = []
        self.svc.on_change = lambda action, data: events.append((action, data))
        self.svc.optimize("p1", "step_a")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "optimized")

    def test_fire_data_contains_action_key(self):
        events = []
        self.svc.on_change = lambda action, data: events.append(data)
        self.svc.optimize("p1", "step_a")
        self.assertIn("action", events[0])
        self.assertEqual(events[0]["action"], "optimized")

    def test_fire_silent_on_error(self):
        self.svc.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("boom"))
        rid = self.svc.optimize("p1", "step_a")
        self.assertTrue(rid.startswith("psop-"))

    def test_unique_ids(self):
        ids = set()
        for i in range(100):
            rid = self.svc.optimize("p1", f"step_{i}")
            ids.add(rid)
        self.assertEqual(len(ids), 100)


if __name__ == "__main__":
    unittest.main()
