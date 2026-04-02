"""Tests for PipelineStepBranch service."""

import sys
import unittest

sys.path.insert(0, ".")
from src.services.pipeline_step_branch import PipelineStepBranch


class TestPipelineStepBranch(unittest.TestCase):

    def setUp(self):
        self.svc = PipelineStepBranch()

    def test_add_branch_returns_id(self):
        bid = self.svc.add_branch("p1", "step1", "status", {"ok": "step2", "fail": "step3"})
        self.assertTrue(bid.startswith("psb-"))
        self.assertEqual(len(bid), 4 + 16)  # prefix + 16 hex chars

    def test_get_branch(self):
        bid = self.svc.add_branch("p1", "step1", "status", {"ok": "step2"})
        branch = self.svc.get_branch(bid)
        self.assertIsNotNone(branch)
        self.assertEqual(branch["pipeline_id"], "p1")
        self.assertEqual(branch["step_name"], "step1")
        self.assertEqual(branch["condition_field"], "status")
        self.assertEqual(branch["branches"], {"ok": "step2"})

    def test_get_branch_not_found(self):
        self.assertIsNone(self.svc.get_branch("psb-nonexistent"))

    def test_evaluate_branch_match(self):
        self.svc.add_branch("p1", "step1", "status", {"ok": "step2", "fail": "step3"})
        result = self.svc.evaluate_branch("p1", "step1", {"status": "ok"})
        self.assertEqual(result, "step2")

    def test_evaluate_branch_no_match_returns_default(self):
        self.svc.add_branch("p1", "step1", "status", {"ok": "step2"})
        result = self.svc.evaluate_branch("p1", "step1", {"status": "unknown"})
        self.assertEqual(result, "default")

    def test_evaluate_branch_missing_field_returns_default(self):
        self.svc.add_branch("p1", "step1", "status", {"ok": "step2"})
        result = self.svc.evaluate_branch("p1", "step1", {"other": "value"})
        self.assertEqual(result, "default")

    def test_evaluate_branch_no_branch_defined(self):
        result = self.svc.evaluate_branch("p1", "step1", {"status": "ok"})
        self.assertEqual(result, "default")

    def test_set_default(self):
        bid = self.svc.add_branch("p1", "step1", "status", {"ok": "step2"})
        self.assertTrue(self.svc.set_default(bid, "error_step"))
        result = self.svc.evaluate_branch("p1", "step1", {"status": "unknown"})
        self.assertEqual(result, "error_step")

    def test_set_default_not_found(self):
        self.assertFalse(self.svc.set_default("psb-nonexistent", "step"))

    def test_remove_branch(self):
        bid = self.svc.add_branch("p1", "step1", "status", {"ok": "step2"})
        self.assertTrue(self.svc.remove_branch(bid))
        self.assertIsNone(self.svc.get_branch(bid))
        self.assertFalse(self.svc.remove_branch(bid))

    def test_get_branches_by_pipeline(self):
        self.svc.add_branch("p1", "step1", "status", {"ok": "step2"})
        self.svc.add_branch("p1", "step2", "type", {"a": "step3"})
        self.svc.add_branch("p2", "step1", "status", {"ok": "step2"})
        branches = self.svc.get_branches("p1")
        self.assertEqual(len(branches), 2)

    def test_get_branches_by_pipeline_and_step(self):
        self.svc.add_branch("p1", "step1", "status", {"ok": "step2"})
        self.svc.add_branch("p1", "step2", "type", {"a": "step3"})
        branches = self.svc.get_branches("p1", "step1")
        self.assertEqual(len(branches), 1)

    def test_get_branch_count(self):
        self.svc.add_branch("p1", "step1", "status", {"ok": "step2"})
        self.svc.add_branch("p2", "step1", "status", {"ok": "step2"})
        self.assertEqual(self.svc.get_branch_count(), 2)
        self.assertEqual(self.svc.get_branch_count("p1"), 1)

    def test_list_pipelines(self):
        self.svc.add_branch("p2", "step1", "s", {})
        self.svc.add_branch("p1", "step1", "s", {})
        pipelines = self.svc.list_pipelines()
        self.assertEqual(pipelines, ["p1", "p2"])

    def test_get_stats(self):
        self.svc.add_branch("p1", "step1", "s", {})
        stats = self.svc.get_stats()
        self.assertEqual(stats["total_branches"], 1)
        self.assertEqual(stats["total_pipelines"], 1)
        self.assertGreater(stats["seq"], 0)

    def test_reset(self):
        self.svc.add_branch("p1", "step1", "s", {})
        self.svc.reset()
        self.assertEqual(self.svc.get_branch_count(), 0)
        self.assertEqual(self.svc.list_pipelines(), [])

    def test_on_change_callback(self):
        events = []
        cb_id = self.svc.on_change(lambda evt, data: events.append((evt, data)))
        self.assertTrue(cb_id.startswith("psb-"))
        self.svc.add_branch("p1", "step1", "s", {"ok": "step2"})
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "add_branch")
        self.assertTrue(self.svc.remove_callback(cb_id))
        self.assertFalse(self.svc.remove_callback(cb_id))

    def test_prune_excess_entries(self):
        svc = PipelineStepBranch()
        svc.MAX_ENTRIES = 5
        for i in range(8):
            svc.add_branch(f"p{i}", "step", "s", {})
        self.assertLessEqual(svc.get_branch_count(), 5)


if __name__ == "__main__":
    unittest.main()
