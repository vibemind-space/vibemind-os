"""Tests for PipelineStepAudit service."""

import sys
import unittest

sys.path.insert(0, ".")
from src.services.pipeline_step_audit import PipelineStepAudit, PipelineStepAuditState


class TestPipelineStepAudit(unittest.TestCase):

    def setUp(self):
        self.audit = PipelineStepAudit()

    def test_log_execution_returns_id(self):
        aid = self.audit.log_execution("p1", "step_a")
        self.assertTrue(aid.startswith("psa2-"))
        self.assertEqual(len(aid), 5 + 16)  # prefix + hash

    def test_get_audit_entry(self):
        aid = self.audit.log_execution("p1", "step_a", executor="alice", status="success")
        entry = self.audit.get_audit_entry(aid)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["pipeline_id"], "p1")
        self.assertEqual(entry["step_name"], "step_a")
        self.assertEqual(entry["executor"], "alice")
        self.assertEqual(entry["status"], "success")

    def test_get_audit_entry_not_found(self):
        self.assertIsNone(self.audit.get_audit_entry("psa2-nonexistent1234"))

    def test_get_audit_trail(self):
        self.audit.log_execution("p1", "step_a")
        self.audit.log_execution("p1", "step_b")
        self.audit.log_execution("p2", "step_a")
        trail = self.audit.get_audit_trail("p1")
        self.assertEqual(len(trail), 2)
        # All entries belong to p1
        for e in trail:
            self.assertEqual(e["pipeline_id"], "p1")

    def test_get_audit_trail_filter_step(self):
        self.audit.log_execution("p1", "step_a")
        self.audit.log_execution("p1", "step_b")
        trail = self.audit.get_audit_trail("p1", step_name="step_a")
        self.assertEqual(len(trail), 1)
        self.assertEqual(trail[0]["step_name"], "step_a")

    def test_get_audit_trail_limit(self):
        for i in range(10):
            self.audit.log_execution("p1", f"step_{i}")
        trail = self.audit.get_audit_trail("p1", limit=3)
        self.assertEqual(len(trail), 3)

    def test_get_audit_summary(self):
        self.audit.log_execution("p1", "step_a", executor="alice", status="success")
        self.audit.log_execution("p1", "step_b", executor="bob", status="failure")
        self.audit.log_execution("p1", "step_a", executor="alice", status="success")
        summary = self.audit.get_audit_summary("p1")
        self.assertEqual(summary["total_executions"], 3)
        self.assertEqual(summary["success_count"], 2)
        self.assertEqual(summary["failure_count"], 1)
        self.assertEqual(summary["unique_steps"], 2)
        self.assertEqual(summary["unique_executors"], 2)

    def test_clear_audit(self):
        self.audit.log_execution("p1", "step_a")
        self.audit.log_execution("p1", "step_b")
        self.audit.log_execution("p2", "step_a")
        cleared = self.audit.clear_audit("p1")
        self.assertEqual(cleared, 2)
        self.assertEqual(self.audit.get_audit_count("p1"), 0)
        self.assertEqual(self.audit.get_audit_count("p2"), 1)

    def test_get_audit_count(self):
        self.audit.log_execution("p1", "step_a")
        self.audit.log_execution("p2", "step_b")
        self.assertEqual(self.audit.get_audit_count(), 2)
        self.assertEqual(self.audit.get_audit_count("p1"), 1)

    def test_list_pipelines(self):
        self.audit.log_execution("p1", "step_a")
        self.audit.log_execution("p2", "step_b")
        self.audit.log_execution("p3", "step_c")
        pipelines = self.audit.list_pipelines()
        self.assertEqual(pipelines, ["p1", "p2", "p3"])

    def test_callbacks(self):
        events = []
        self.audit.on_change("cb1", lambda evt, data: events.append((evt, data)))
        self.audit.log_execution("p1", "step_a")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "execution_logged")
        # Remove callback
        self.assertTrue(self.audit.remove_callback("cb1"))
        self.assertFalse(self.audit.remove_callback("cb1"))
        self.audit.log_execution("p1", "step_b")
        self.assertEqual(len(events), 1)  # No new event

    def test_unique_ids(self):
        ids = set()
        for i in range(100):
            aid = self.audit.log_execution("p1", "step_a")
            ids.add(aid)
        self.assertEqual(len(ids), 100)

    def test_prune_max_entries(self):
        original_max = PipelineStepAudit.MAX_ENTRIES
        PipelineStepAudit.MAX_ENTRIES = 10
        try:
            for i in range(15):
                self.audit.log_execution("p1", f"step_{i}")
            self.assertLessEqual(self.audit.get_audit_count(), 10)
        finally:
            PipelineStepAudit.MAX_ENTRIES = original_max

    def test_get_stats(self):
        self.audit.log_execution("p1", "step_a")
        self.audit.log_execution("p2", "step_b")
        stats = self.audit.get_stats()
        self.assertEqual(stats["total_entries"], 2)
        self.assertEqual(stats["total_pipelines"], 2)
        self.assertGreaterEqual(stats["seq"], 2)

    def test_reset(self):
        self.audit.log_execution("p1", "step_a")
        self.audit.on_change("cb1", lambda e, d: None)
        self.audit.reset()
        self.assertEqual(self.audit.get_audit_count(), 0)
        self.assertEqual(len(self.audit._callbacks), 0)

    def test_state_dataclass(self):
        state = PipelineStepAuditState()
        self.assertEqual(state.entries, {})
        self.assertEqual(state._seq, 0)

    def test_log_execution_with_all_params(self):
        aid = self.audit.log_execution(
            "p1", "step_a",
            executor="bob",
            input_summary="input data",
            output_summary="output data",
            status="failure",
        )
        entry = self.audit.get_audit_entry(aid)
        self.assertEqual(entry["executor"], "bob")
        self.assertEqual(entry["input_summary"], "input data")
        self.assertEqual(entry["output_summary"], "output data")
        self.assertEqual(entry["status"], "failure")
        self.assertIn("timestamp", entry)


if __name__ == "__main__":
    unittest.main()
