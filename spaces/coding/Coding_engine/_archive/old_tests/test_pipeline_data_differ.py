"""Tests for PipelineDataDiffer service."""

import sys
import unittest

sys.path.insert(0, ".")
from src.services.pipeline_data_differ import PipelineDataDiffer, PipelineDataDifferState


class TestPipelineDataDiffer(unittest.TestCase):
    """Test suite for PipelineDataDiffer."""

    def setUp(self):
        self.differ = PipelineDataDiffer()

    def test_compare_added_records(self):
        """Records in new but not old should appear as added."""
        old = []
        new = [{"id": "a", "value": 1}, {"id": "b", "value": 2}]
        result = self.differ.compare("pipe1", old, new, "id")
        self.assertEqual(len(result["added"]), 2)
        self.assertEqual(len(result["removed"]), 0)
        self.assertEqual(len(result["changed"]), 0)
        self.assertEqual(result["unchanged"], 0)

    def test_compare_removed_records(self):
        """Records in old but not new should appear as removed."""
        old = [{"id": "a", "value": 1}, {"id": "b", "value": 2}]
        new = []
        result = self.differ.compare("pipe1", old, new, "id")
        self.assertEqual(len(result["added"]), 0)
        self.assertEqual(len(result["removed"]), 2)

    def test_compare_changed_records(self):
        """Records present in both but different should appear as changed."""
        old = [{"id": "a", "value": 1}]
        new = [{"id": "a", "value": 99}]
        result = self.differ.compare("pipe1", old, new, "id")
        self.assertEqual(len(result["changed"]), 1)
        self.assertEqual(result["changed"][0]["old"]["value"], 1)
        self.assertEqual(result["changed"][0]["new"]["value"], 99)
        self.assertEqual(result["unchanged"], 0)

    def test_compare_unchanged_records(self):
        """Identical records should be counted as unchanged."""
        old = [{"id": "a", "value": 1}]
        new = [{"id": "a", "value": 1}]
        result = self.differ.compare("pipe1", old, new, "id")
        self.assertEqual(result["unchanged"], 1)
        self.assertEqual(len(result["added"]), 0)
        self.assertEqual(len(result["removed"]), 0)
        self.assertEqual(len(result["changed"]), 0)

    def test_compare_mixed(self):
        """Mixed scenario with adds, removes, changes, and unchanged."""
        old = [{"id": "a", "v": 1}, {"id": "b", "v": 2}, {"id": "c", "v": 3}]
        new = [{"id": "b", "v": 2}, {"id": "c", "v": 99}, {"id": "d", "v": 4}]
        result = self.differ.compare("pipe1", old, new, "id")
        self.assertEqual(len(result["added"]), 1)
        self.assertEqual(len(result["removed"]), 1)
        self.assertEqual(len(result["changed"]), 1)
        self.assertEqual(result["unchanged"], 1)

    def test_get_diff_summary(self):
        """get_diff_summary returns last comparison summary."""
        self.assertIsNone(self.differ.get_diff_summary("pipe1"))
        self.differ.compare("pipe1", [], [{"id": "a"}], "id")
        summary = self.differ.get_diff_summary("pipe1")
        self.assertIsNotNone(summary)
        self.assertEqual(summary["pipeline_id"], "pipe1")
        self.assertEqual(summary["summary"]["added_count"], 1)

    def test_get_history(self):
        """get_history returns past diffs with limit."""
        for i in range(5):
            self.differ.compare("pipe1", [], [{"id": str(i)}], "id")
        history = self.differ.get_history("pipe1", limit=3)
        self.assertEqual(len(history), 3)
        full_history = self.differ.get_history("pipe1")
        self.assertEqual(len(full_history), 5)

    def test_get_diff_count(self):
        """get_diff_count counts diffs per pipeline or globally."""
        self.differ.compare("pipe1", [], [{"id": "a"}], "id")
        self.differ.compare("pipe1", [], [{"id": "b"}], "id")
        self.differ.compare("pipe2", [], [{"id": "c"}], "id")
        self.assertEqual(self.differ.get_diff_count("pipe1"), 2)
        self.assertEqual(self.differ.get_diff_count("pipe2"), 1)
        self.assertEqual(self.differ.get_diff_count(), 3)

    def test_list_pipelines(self):
        """list_pipelines returns sorted pipeline IDs."""
        self.differ.compare("z_pipe", [], [{"id": "a"}], "id")
        self.differ.compare("a_pipe", [], [{"id": "b"}], "id")
        pipelines = self.differ.list_pipelines()
        self.assertEqual(pipelines, ["a_pipe", "z_pipe"])

    def test_callbacks(self):
        """on_change, remove_callback, and _fire work correctly."""
        events = []
        cb_id = self.differ.on_change(lambda e: events.append(e))
        self.assertTrue(cb_id.startswith("pdd2-"))
        self.differ.compare("pipe1", [], [{"id": "a"}], "id")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "diff_completed")
        self.assertEqual(events[0]["pipeline_id"], "pipe1")
        # Remove callback
        self.assertTrue(self.differ.remove_callback(cb_id))
        self.assertFalse(self.differ.remove_callback("nonexistent"))
        self.differ.compare("pipe1", [], [{"id": "b"}], "id")
        self.assertEqual(len(events), 1)  # No new event

    def test_get_stats_and_reset(self):
        """get_stats returns correct counts, reset clears everything."""
        self.differ.on_change(lambda e: None)
        self.differ.compare("pipe1", [], [{"id": "a"}], "id")
        stats = self.differ.get_stats()
        self.assertEqual(stats["pipeline_count"], 1)
        self.assertEqual(stats["total_diffs"], 1)
        self.assertEqual(stats["callbacks_registered"], 1)
        self.differ.reset()
        stats = self.differ.get_stats()
        self.assertEqual(stats["pipeline_count"], 0)
        self.assertEqual(stats["total_diffs"], 0)
        self.assertEqual(stats["callbacks_registered"], 0)

    def test_id_prefix(self):
        """Generated IDs use the pdd2- prefix."""
        self.differ.compare("pipe1", [], [{"id": "a"}], "id")
        summary = self.differ.get_diff_summary("pipe1")
        self.assertTrue(summary["id"].startswith("pdd2-"))

    def test_prune_max_entries(self):
        """Pruning keeps entries within MAX_ENTRIES limit."""
        self.differ.MAX_ENTRIES = 5
        for i in range(8):
            self.differ.compare(f"pipe_{i}", [], [{"id": str(i)}], "id")
        total = self.differ.get_diff_count()
        self.assertLessEqual(total, 5)

    def test_state_dataclass(self):
        """PipelineDataDifferState initializes correctly."""
        state = PipelineDataDifferState()
        self.assertEqual(state.entries, {})
        self.assertEqual(state._seq, 0)


if __name__ == "__main__":
    unittest.main()
