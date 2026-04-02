"""Tests for PipelineStepRollback service."""

import sys
import unittest

sys.path.insert(0, ".")
from src.services.pipeline_step_rollback import PipelineStepRollback, PipelineStepRollbackState


class TestPipelineStepRollback(unittest.TestCase):

    def setUp(self):
        self.rb = PipelineStepRollback()

    def test_save_checkpoint_returns_id(self):
        cid = self.rb.save_checkpoint("p1", "step1", {"key": "value"})
        self.assertTrue(cid.startswith("psrb-"))
        self.assertEqual(len(cid), 5 + 16)  # prefix + hash

    def test_get_checkpoint(self):
        cid = self.rb.save_checkpoint("p1", "step1", {"a": 1})
        result = self.rb.get_checkpoint(cid)
        self.assertIsNotNone(result)
        self.assertEqual(result["state_data"], {"a": 1})
        self.assertEqual(result["pipeline_id"], "p1")
        self.assertEqual(result["step_name"], "step1")

    def test_get_checkpoint_not_found(self):
        result = self.rb.get_checkpoint("psrb-nonexistent")
        self.assertIsNone(result)

    def test_rollback_returns_latest_state(self):
        self.rb.save_checkpoint("p1", "step1", {"version": 1})
        self.rb.save_checkpoint("p1", "step1", {"version": 2})
        self.rb.save_checkpoint("p1", "step1", {"version": 3})
        result = self.rb.rollback("p1", "step1")
        self.assertEqual(result["version"], 3)

    def test_rollback_returns_none_when_empty(self):
        result = self.rb.rollback("p1", "step1")
        self.assertIsNone(result)

    def test_get_checkpoints_filtered(self):
        self.rb.save_checkpoint("p1", "step1", {"a": 1})
        self.rb.save_checkpoint("p1", "step2", {"b": 2})
        self.rb.save_checkpoint("p2", "step1", {"c": 3})
        results = self.rb.get_checkpoints("p1", "step1")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["state_data"], {"a": 1})

    def test_get_checkpoints_all_for_pipeline(self):
        self.rb.save_checkpoint("p1", "step1", {"a": 1})
        self.rb.save_checkpoint("p1", "step2", {"b": 2})
        self.rb.save_checkpoint("p2", "step1", {"c": 3})
        results = self.rb.get_checkpoints("p1")
        self.assertEqual(len(results), 2)

    def test_delete_checkpoint(self):
        cid = self.rb.save_checkpoint("p1", "step1", {"a": 1})
        self.assertTrue(self.rb.delete_checkpoint(cid))
        self.assertIsNone(self.rb.get_checkpoint(cid))
        self.assertFalse(self.rb.delete_checkpoint(cid))

    def test_get_checkpoint_count(self):
        self.rb.save_checkpoint("p1", "step1", {"a": 1})
        self.rb.save_checkpoint("p1", "step2", {"b": 2})
        self.rb.save_checkpoint("p2", "step1", {"c": 3})
        self.assertEqual(self.rb.get_checkpoint_count(), 3)
        self.assertEqual(self.rb.get_checkpoint_count("p1"), 2)
        self.assertEqual(self.rb.get_checkpoint_count("p2"), 1)
        self.assertEqual(self.rb.get_checkpoint_count("p99"), 0)

    def test_list_pipelines(self):
        self.rb.save_checkpoint("p1", "s1", {})
        self.rb.save_checkpoint("p2", "s1", {})
        self.rb.save_checkpoint("p3", "s1", {})
        self.rb.save_checkpoint("p1", "s2", {})
        pipelines = self.rb.list_pipelines()
        self.assertEqual(pipelines, ["p1", "p2", "p3"])

    def test_get_stats(self):
        self.rb.save_checkpoint("p1", "s1", {})
        self.rb.save_checkpoint("p2", "s1", {})
        stats = self.rb.get_stats()
        self.assertEqual(stats["total_checkpoints"], 2)
        self.assertEqual(stats["total_pipelines"], 2)
        self.assertEqual(stats["max_entries"], 10000)
        self.assertIn("seq", stats)

    def test_reset(self):
        self.rb.save_checkpoint("p1", "s1", {"a": 1})
        self.rb.add_callback("cb1", lambda e, d: None)
        self.rb.reset()
        self.assertEqual(self.rb.get_checkpoint_count(), 0)
        self.assertEqual(self.rb.list_pipelines(), [])
        stats = self.rb.get_stats()
        self.assertEqual(stats["callbacks"], 0)

    def test_callbacks_and_on_change(self):
        events = []
        self.rb.on_change = lambda e, d: events.append(("on_change", e))
        self.rb.add_callback("cb1", lambda e, d: events.append(("cb1", e)))
        self.rb.save_checkpoint("p1", "s1", {})
        self.assertIn(("on_change", "save_checkpoint"), events)
        self.assertIn(("cb1", "save_checkpoint"), events)

    def test_remove_callback(self):
        self.rb.add_callback("cb1", lambda e, d: None)
        self.assertTrue(self.rb.remove_callback("cb1"))
        self.assertFalse(self.rb.remove_callback("cb1"))

    def test_unique_ids(self):
        ids = set()
        for i in range(100):
            cid = self.rb.save_checkpoint("p1", "s1", {"i": i})
            ids.add(cid)
        self.assertEqual(len(ids), 100)

    def test_prune_max_entries(self):
        self.rb.MAX_ENTRIES = 50
        for i in range(60):
            self.rb.save_checkpoint("p1", "s1", {"i": i})
        self.assertLessEqual(self.rb.get_checkpoint_count(), 50)

    def test_dataclass_state(self):
        state = PipelineStepRollbackState()
        self.assertEqual(state.entries, {})
        self.assertEqual(state._seq, 0)


if __name__ == "__main__":
    unittest.main()
