"""Tests for PipelineStepEnabler service."""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_step_enabler import PipelineStepEnabler


class TestPipelineStepEnabler(unittest.TestCase):
    """Tests for PipelineStepEnabler."""

    def setUp(self):
        self.svc = PipelineStepEnabler()

    # -- enable ----------------------------------------------------------

    def test_enable_returns_id(self):
        eid = self.svc.enable("p1", "step_a", "activate feature")
        self.assertIsInstance(eid, str)
        self.assertTrue(eid.startswith("psen-"))

    def test_enable_stores_fields(self):
        eid = self.svc.enable("p1", "step_a", "needed", metadata={"tag": "v1"})
        entry = self.svc.get_enablement(eid)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["pipeline_id"], "p1")
        self.assertEqual(entry["step_name"], "step_a")
        self.assertEqual(entry["reason"], "needed")
        self.assertEqual(entry["metadata"], {"tag": "v1"})
        self.assertIn("created_at", entry)
        self.assertIn("updated_at", entry)

    def test_enable_default_reason(self):
        eid = self.svc.enable("p1", "step_a")
        entry = self.svc.get_enablement(eid)
        self.assertEqual(entry["reason"], "")

    def test_enable_default_metadata(self):
        eid = self.svc.enable("p1", "step_a", "reason")
        entry = self.svc.get_enablement(eid)
        self.assertEqual(entry["metadata"], {})

    def test_enable_with_complex_metadata(self):
        meta = {"score": 0.95, "tags": ["a", "b"], "nested": {"x": 1}}
        eid = self.svc.enable("p1", "step_a", "complex", metadata=meta)
        entry = self.svc.get_enablement(eid)
        self.assertEqual(entry["metadata"], meta)

    def test_enable_empty_reason(self):
        eid = self.svc.enable("p1", "step_a", "")
        entry = self.svc.get_enablement(eid)
        self.assertEqual(entry["reason"], "")

    # -- get_enablement --------------------------------------------------

    def test_get_enablement_not_found(self):
        result = self.svc.get_enablement("nonexistent")
        self.assertIsNone(result)

    def test_get_enablement_returns_copy(self):
        eid = self.svc.enable("p1", "step_a", "reason")
        entry = self.svc.get_enablement(eid)
        entry["pipeline_id"] = "modified"
        original = self.svc.get_enablement(eid)
        self.assertEqual(original["pipeline_id"], "p1")

    # -- get_enablements -------------------------------------------------

    def test_get_enablements_empty(self):
        result = self.svc.get_enablements()
        self.assertEqual(result, [])

    def test_get_enablements_newest_first(self):
        eid1 = self.svc.enable("p1", "step_a", "r1")
        eid2 = self.svc.enable("p1", "step_b", "r2")
        eid3 = self.svc.enable("p1", "step_c", "r3")
        result = self.svc.get_enablements()
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["enablement_id"], eid3)
        self.assertEqual(result[2]["enablement_id"], eid1)

    def test_get_enablements_filter_by_pipeline(self):
        self.svc.enable("p1", "step_a", "r1")
        self.svc.enable("p2", "step_b", "r2")
        self.svc.enable("p1", "step_c", "r3")
        result = self.svc.get_enablements(pipeline_id="p1")
        self.assertEqual(len(result), 2)
        for r in result:
            self.assertEqual(r["pipeline_id"], "p1")

    def test_get_enablements_limit(self):
        for i in range(10):
            self.svc.enable("p1", f"step_{i}", f"reason_{i}")
        result = self.svc.get_enablements(limit=3)
        self.assertEqual(len(result), 3)

    def test_get_enablements_returns_dicts(self):
        self.svc.enable("p1", "step_a", "reason")
        result = self.svc.get_enablements()
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], dict)
        self.assertIn("enablement_id", result[0])

    def test_get_enablements_no_match(self):
        self.svc.enable("p1", "step_a", "reason")
        result = self.svc.get_enablements(pipeline_id="p99")
        self.assertEqual(result, [])

    # -- get_enablement_count --------------------------------------------

    def test_get_enablement_count_all(self):
        self.svc.enable("p1", "step_a", "r1")
        self.svc.enable("p2", "step_b", "r2")
        self.assertEqual(self.svc.get_enablement_count(), 2)

    def test_get_enablement_count_by_pipeline(self):
        self.svc.enable("p1", "step_a", "r1")
        self.svc.enable("p2", "step_b", "r2")
        self.svc.enable("p1", "step_c", "r3")
        self.assertEqual(self.svc.get_enablement_count(pipeline_id="p1"), 2)
        self.assertEqual(self.svc.get_enablement_count(pipeline_id="p2"), 1)
        self.assertEqual(self.svc.get_enablement_count(pipeline_id="p3"), 0)

    def test_get_enablement_count_empty(self):
        self.assertEqual(self.svc.get_enablement_count(), 0)

    # -- get_stats -------------------------------------------------------

    def test_get_stats_empty(self):
        stats = self.svc.get_stats()
        self.assertEqual(stats["total_enablements"], 0)
        self.assertEqual(stats["unique_pipelines"], 0)

    def test_get_stats_with_data(self):
        self.svc.enable("p1", "step_a", "r1")
        self.svc.enable("p1", "step_b", "r2")
        self.svc.enable("p2", "step_a", "r3")
        stats = self.svc.get_stats()
        self.assertEqual(stats["total_enablements"], 3)
        self.assertEqual(stats["unique_pipelines"], 2)

    # -- reset -----------------------------------------------------------

    def test_reset(self):
        self.svc.enable("p1", "step_a", "r1")
        self.svc.enable("p2", "step_b", "r2")
        self.svc.reset()
        self.assertEqual(self.svc.get_enablement_count(), 0)
        self.assertEqual(self.svc.get_stats()["total_enablements"], 0)

    def test_reset_clears_callbacks(self):
        self.svc.on_change = lambda a, d: None
        self.svc.reset()
        self.assertIsNone(self.svc.on_change)

    def test_reset_allows_new_entries(self):
        self.svc.enable("p1", "step_a", "r1")
        self.svc.reset()
        eid = self.svc.enable("p2", "step_b", "r2")
        self.assertEqual(self.svc.get_enablement_count(), 1)
        self.assertIsNotNone(self.svc.get_enablement(eid))

    # -- callbacks -------------------------------------------------------

    def test_on_change_property(self):
        self.assertIsNone(self.svc.on_change)
        events = []
        self.svc.on_change = lambda action, data: events.append((action, data))
        self.svc.enable("p1", "step_a", "reason")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "enabled")

    def test_on_change_set_none(self):
        self.svc.on_change = lambda a, d: None
        self.assertIsNotNone(self.svc.on_change)
        self.svc.on_change = None
        self.assertIsNone(self.svc.on_change)

    def test_remove_callback(self):
        self.svc.on_change = lambda a, d: None
        self.assertTrue(self.svc.remove_callback("__on_change__"))
        self.assertIsNone(self.svc.on_change)

    def test_remove_callback_not_found(self):
        self.assertFalse(self.svc.remove_callback("nonexistent"))

    def test_fire_silent_on_error(self):
        self.svc.on_change = lambda a, d: (_ for _ in ()).throw(RuntimeError("boom"))
        eid = self.svc.enable("p1", "step_a", "reason")
        self.assertTrue(eid.startswith("psen-"))

    def test_fire_event_on_enable(self):
        events = []
        self.svc.on_change = lambda action, data: events.append(action)
        self.svc.enable("p1", "step_a", "reason")
        self.assertIn("enabled", events)

    # -- ID generation ---------------------------------------------------

    def test_unique_ids(self):
        ids = set()
        for i in range(100):
            eid = self.svc.enable("p1", f"step_{i}", f"reason_{i}")
            ids.add(eid)
        self.assertEqual(len(ids), 100)

    def test_id_prefix(self):
        eid = self.svc.enable("p1", "step_a", "reason")
        self.assertTrue(eid.startswith("psen-"))

    # -- pruning ---------------------------------------------------------

    def test_prune_oldest_quarter(self):
        self.svc.MAX_ENTRIES = 10
        for i in range(12):
            self.svc.enable("p1", f"step_{i}", f"reason_{i}")
        self.assertLessEqual(self.svc.get_enablement_count(), 12)

    def test_prune_keeps_newest(self):
        self.svc.MAX_ENTRIES = 4
        eids = []
        for i in range(6):
            eids.append(self.svc.enable("p1", f"step_{i}", f"reason_{i}"))
        remaining = self.svc.get_enablements(limit=100)
        remaining_ids = {r["enablement_id"] for r in remaining}
        # The newest entry should always survive pruning
        self.assertIn(eids[-1], remaining_ids)


if __name__ == "__main__":
    unittest.main()
