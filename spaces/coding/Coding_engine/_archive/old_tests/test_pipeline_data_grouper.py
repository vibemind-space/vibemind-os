"""Tests for PipelineDataGrouper."""

import sys
import unittest

sys.path.insert(0, ".")
from src.services.pipeline_data_grouper import PipelineDataGrouper, PipelineDataGrouperState


class TestPipelineDataGrouper(unittest.TestCase):
    """Tests for PipelineDataGrouper."""

    def setUp(self):
        self.grouper = PipelineDataGrouper()

    def test_configure_returns_id_with_prefix(self):
        config_id = self.grouper.configure("pipe1", ["region"])
        self.assertTrue(config_id.startswith("pdg-"))
        self.assertEqual(len(config_id), 4 + 16)  # prefix + hash

    def test_configure_and_get_config(self):
        self.grouper.configure("pipe1", ["region", "status"])
        config = self.grouper.get_config("pipe1")
        self.assertIsNotNone(config)
        self.assertEqual(config["pipeline_id"], "pipe1")
        self.assertEqual(config["group_keys"], ["region", "status"])

    def test_get_config_nonexistent(self):
        result = self.grouper.get_config("nonexistent")
        self.assertIsNone(result)

    def test_group_by_single_key(self):
        self.grouper.configure("pipe1", ["region"])
        records = [
            {"region": "us", "value": 10},
            {"region": "eu", "value": 20},
            {"region": "us", "value": 30},
        ]
        groups = self.grouper.group("pipe1", records)
        self.assertEqual(len(groups), 2)
        self.assertEqual(len(groups[("us",)]), 2)
        self.assertEqual(len(groups[("eu",)]), 1)

    def test_group_by_multiple_keys(self):
        self.grouper.configure("pipe1", ["region", "status"])
        records = [
            {"region": "us", "status": "active", "value": 10},
            {"region": "us", "status": "inactive", "value": 20},
            {"region": "us", "status": "active", "value": 30},
        ]
        groups = self.grouper.group("pipe1", records)
        self.assertEqual(len(groups), 2)
        self.assertEqual(len(groups[("us", "active")]), 2)
        self.assertEqual(len(groups[("us", "inactive")]), 1)

    def test_group_without_config_raises(self):
        with self.assertRaises(ValueError):
            self.grouper.group("nonexistent", [{"a": 1}])

    def test_aggregate_sum(self):
        self.grouper.configure("pipe1", ["region"], agg_config={"value": "sum"})
        records = [
            {"region": "us", "value": 10},
            {"region": "us", "value": 20},
            {"region": "eu", "value": 5},
        ]
        results = self.grouper.aggregate("pipe1", records)
        self.assertEqual(len(results), 2)
        by_region = {r["region"]: r for r in results}
        self.assertEqual(by_region["us"]["value"], 30)
        self.assertEqual(by_region["eu"]["value"], 5)

    def test_aggregate_multiple_functions(self):
        self.grouper.configure("pipe1", ["region"], agg_config={
            "value": "avg",
            "count_field": "count",
            "score": "max",
        })
        records = [
            {"region": "us", "value": 10, "count_field": 1, "score": 80},
            {"region": "us", "value": 20, "count_field": 1, "score": 90},
        ]
        results = self.grouper.aggregate("pipe1", records)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["value"], 15.0)
        self.assertEqual(results[0]["count_field"], 2)
        self.assertEqual(results[0]["score"], 90)

    def test_aggregate_first_last(self):
        self.grouper.configure("pipe1", ["g"], agg_config={"v": "first", "w": "last"})
        records = [
            {"g": "a", "v": 1, "w": 10},
            {"g": "a", "v": 2, "w": 20},
            {"g": "a", "v": 3, "w": 30},
        ]
        results = self.grouper.aggregate("pipe1", records)
        self.assertEqual(results[0]["v"], 1)
        self.assertEqual(results[0]["w"], 30)

    def test_aggregate_min(self):
        self.grouper.configure("pipe1", ["g"], agg_config={"v": "min"})
        records = [
            {"g": "a", "v": 5},
            {"g": "a", "v": 2},
            {"g": "a", "v": 8},
        ]
        results = self.grouper.aggregate("pipe1", records)
        self.assertEqual(results[0]["v"], 2)

    def test_remove_config(self):
        config_id = self.grouper.configure("pipe1", ["region"])
        self.assertTrue(self.grouper.remove_config(config_id))
        self.assertIsNone(self.grouper.get_config("pipe1"))
        self.assertFalse(self.grouper.remove_config(config_id))

    def test_get_config_count(self):
        self.assertEqual(self.grouper.get_config_count(), 0)
        self.grouper.configure("pipe1", ["a"])
        self.grouper.configure("pipe2", ["b"])
        self.assertEqual(self.grouper.get_config_count(), 2)
        self.assertEqual(self.grouper.get_config_count("pipe1"), 1)
        self.assertEqual(self.grouper.get_config_count("nonexistent"), 0)

    def test_list_pipelines(self):
        self.grouper.configure("pipe1", ["a"])
        self.grouper.configure("pipe2", ["b"])
        pipelines = self.grouper.list_pipelines()
        self.assertIn("pipe1", pipelines)
        self.assertIn("pipe2", pipelines)
        self.assertEqual(len(pipelines), 2)

    def test_callbacks(self):
        events = []
        self.grouper.on_change("test_cb", lambda action, detail: events.append((action, detail)))
        self.grouper.configure("pipe1", ["a"])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "configure")
        self.assertTrue(self.grouper.remove_callback("test_cb"))
        self.assertFalse(self.grouper.remove_callback("test_cb"))

    def test_get_stats(self):
        self.grouper.configure("pipe1", ["a"])
        stats = self.grouper.get_stats()
        self.assertEqual(stats["config_count"], 1)
        self.assertEqual(stats["pipeline_count"], 1)
        self.assertIn("seq", stats)
        self.assertIn("callback_count", stats)

    def test_reset(self):
        self.grouper.configure("pipe1", ["a"])
        self.grouper.reset()
        self.assertEqual(self.grouper.get_config_count(), 0)
        self.assertEqual(self.grouper.list_pipelines(), [])
        stats = self.grouper.get_stats()
        self.assertEqual(stats["config_count"], 0)

    def test_unique_ids(self):
        id1 = self.grouper.configure("pipe1", ["a"])
        id2 = self.grouper.configure("pipe2", ["b"])
        self.assertNotEqual(id1, id2)

    def test_state_dataclass(self):
        state = PipelineDataGrouperState()
        self.assertEqual(state.entries, {})
        self.assertEqual(state._seq, 0)


if __name__ == "__main__":
    unittest.main()
