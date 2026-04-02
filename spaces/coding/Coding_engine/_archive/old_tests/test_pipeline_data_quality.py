"""Tests for PipelineDataQuality service."""

import sys
import unittest

sys.path.insert(0, ".")
from src.services.pipeline_data_quality import PipelineDataQuality, PipelineDataQualityState


class TestPipelineDataQuality(unittest.TestCase):

    def setUp(self):
        self.dq = PipelineDataQuality()

    def test_add_rule_returns_id_with_prefix(self):
        rule_id = self.dq.add_rule("pipe1", "name")
        self.assertTrue(rule_id.startswith("pdq-"))

    def test_get_rules_returns_added_rules(self):
        self.dq.add_rule("pipe1", "name", "not_null")
        self.dq.add_rule("pipe1", "email", "not_null")
        self.dq.add_rule("pipe2", "age", "in_range")
        rules = self.dq.get_rules("pipe1")
        self.assertEqual(len(rules), 2)

    def test_remove_rule(self):
        rule_id = self.dq.add_rule("pipe1", "name")
        self.assertTrue(self.dq.remove_rule(rule_id))
        self.assertFalse(self.dq.remove_rule(rule_id))
        self.assertEqual(self.dq.get_rule_count("pipe1"), 0)

    def test_get_rule(self):
        rule_id = self.dq.add_rule("pipe1", "name", "not_null", 0.9)
        rule = self.dq.get_rule(rule_id)
        self.assertIsNotNone(rule)
        self.assertEqual(rule["field"], "name")
        self.assertEqual(rule["rule_type"], "not_null")
        self.assertEqual(rule["threshold"], 0.9)
        self.assertIsNone(self.dq.get_rule("nonexistent"))

    def test_assess_not_null(self):
        self.dq.add_rule("pipe1", "name", "not_null", 0.8)
        records = [{"name": "Alice"}, {"name": "Bob"}, {"name": None}, {"name": "Charlie"}]
        result = self.dq.assess("pipe1", records)
        self.assertEqual(result["total_records"], 4)
        self.assertIn("details", result)
        self.assertIsInstance(result["score"], float)

    def test_assess_empty_records(self):
        self.dq.add_rule("pipe1", "name", "not_null")
        result = self.dq.assess("pipe1", [])
        self.assertEqual(result["score"], 1.0)
        self.assertEqual(result["total_records"], 0)

    def test_assess_no_rules(self):
        result = self.dq.assess("pipe1", [{"name": "Alice"}])
        self.assertEqual(result["score"], 1.0)

    def test_assess_unique(self):
        self.dq.add_rule("pipe1", "id", "unique", 1.0)
        records = [{"id": 1}, {"id": 2}, {"id": 3}]
        result = self.dq.assess("pipe1", records)
        self.assertEqual(result["score"], 1.0)
        # Now with duplicates
        self.dq2 = PipelineDataQuality()
        self.dq2.add_rule("pipe1", "id", "unique", 1.0)
        dup_records = [{"id": 1}, {"id": 1}, {"id": 2}]
        result2 = self.dq2.assess("pipe1", dup_records)
        self.assertLess(result2["score"], 1.0)

    def test_get_history(self):
        self.dq.add_rule("pipe1", "name", "not_null")
        self.dq.assess("pipe1", [{"name": "A"}])
        self.dq.assess("pipe1", [{"name": "B"}])
        self.dq.assess("pipe1", [{"name": "C"}])
        history = self.dq.get_history("pipe1", limit=2)
        self.assertEqual(len(history), 2)

    def test_get_rule_count(self):
        self.dq.add_rule("pipe1", "a")
        self.dq.add_rule("pipe1", "b")
        self.dq.add_rule("pipe2", "c")
        self.assertEqual(self.dq.get_rule_count("pipe1"), 2)
        self.assertEqual(self.dq.get_rule_count(), 3)

    def test_list_pipelines(self):
        self.dq.add_rule("pipe1", "a")
        self.dq.add_rule("pipe2", "b")
        pipes = self.dq.list_pipelines()
        self.assertEqual(sorted(pipes), ["pipe1", "pipe2"])

    def test_callbacks(self):
        events = []
        cb_id = self.dq.on_change(lambda e, d: events.append(e))
        self.dq.add_rule("pipe1", "name")
        self.assertIn("rule_added", events)
        self.assertTrue(self.dq.remove_callback(cb_id))
        self.assertFalse(self.dq.remove_callback(cb_id))

    def test_get_stats_and_reset(self):
        self.dq.add_rule("pipe1", "name")
        self.dq.assess("pipe1", [{"name": "A"}])
        stats = self.dq.get_stats()
        self.assertEqual(stats["total_rules"], 1)
        self.assertGreater(stats["total_assessments"], 0)
        self.dq.reset()
        stats2 = self.dq.get_stats()
        self.assertEqual(stats2["total_rules"], 0)

    def test_invalid_rule_type(self):
        with self.assertRaises(ValueError):
            self.dq.add_rule("pipe1", "name", "invalid_type")

    def test_state_dataclass(self):
        state = PipelineDataQualityState()
        self.assertEqual(state.entries, {})
        self.assertEqual(state._seq, 0)

    def test_prune_max_entries(self):
        dq = PipelineDataQuality()
        dq.MAX_ENTRIES = 5
        for i in range(8):
            dq.add_rule(f"pipe{i}", "field")
        self.assertLessEqual(len(dq._state.entries), 5)


if __name__ == "__main__":
    unittest.main()
