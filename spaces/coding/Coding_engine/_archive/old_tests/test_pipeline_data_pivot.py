"""Tests for PipelineDataPivot service."""

import sys
import unittest

sys.path.insert(0, ".")
from src.services.pipeline_data_pivot import PipelineDataPivot, PipelineDataPivotState


class TestPipelineDataPivot(unittest.TestCase):

    def setUp(self):
        self.pivot = PipelineDataPivot()

    def test_configure_pivot_returns_id(self):
        config_id = self.pivot.configure_pivot("pipe1", "region", "sales")
        self.assertTrue(config_id.startswith("pdp2-"))
        self.assertEqual(len(config_id), 5 + 16)  # "pdp2-" + 16 hex chars

    def test_get_config(self):
        self.pivot.configure_pivot("pipe1", "region", "sales", agg="sum")
        cfg = self.pivot.get_config("pipe1")
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg["pipeline_id"], "pipe1")
        self.assertEqual(cfg["pivot_column"], "region")
        self.assertEqual(cfg["value_column"], "sales")
        self.assertEqual(cfg["agg"], "sum")

    def test_get_config_not_found(self):
        self.assertIsNone(self.pivot.get_config("nonexistent"))

    def test_remove_config(self):
        config_id = self.pivot.configure_pivot("pipe1", "region", "sales")
        self.assertTrue(self.pivot.remove_config(config_id))
        self.assertIsNone(self.pivot.get_config("pipe1"))

    def test_remove_config_not_found(self):
        self.assertFalse(self.pivot.remove_config("pdp2-nonexistent"))

    def test_get_config_count(self):
        self.pivot.configure_pivot("pipe1", "region", "sales")
        self.pivot.configure_pivot("pipe2", "category", "amount")
        self.assertEqual(self.pivot.get_config_count(), 2)
        self.assertEqual(self.pivot.get_config_count("pipe1"), 1)
        self.assertEqual(self.pivot.get_config_count("pipe99"), 0)

    def test_list_pipelines(self):
        self.pivot.configure_pivot("pipe1", "region", "sales")
        self.pivot.configure_pivot("pipe2", "category", "amount")
        pipelines = self.pivot.list_pipelines()
        self.assertIn("pipe1", pipelines)
        self.assertIn("pipe2", pipelines)

    def test_pivot_basic(self):
        self.pivot.configure_pivot("pipe1", "region", "sales")
        records = [
            {"name": "Alice", "region": "East", "sales": 100},
            {"name": "Alice", "region": "West", "sales": 200},
            {"name": "Bob", "region": "East", "sales": 150},
        ]
        result = self.pivot.pivot("pipe1", records)
        self.assertEqual(len(result), 2)
        alice_row = [r for r in result if r.get("name") == "Alice"][0]
        self.assertEqual(alice_row["East"], 100)
        self.assertEqual(alice_row["West"], 200)

    def test_pivot_no_config_raises(self):
        with self.assertRaises(ValueError):
            self.pivot.pivot("no_config", [{"a": 1}])

    def test_unpivot_basic(self):
        self.pivot.configure_pivot("pipe1", "region", "sales")
        records = [
            {"name": "Alice", "East": 100, "West": 200},
            {"name": "Bob", "East": 150, "West": 300},
        ]
        result = self.pivot.unpivot("pipe1", records, ["East", "West"], var_name="region", value_name="sales")
        self.assertEqual(len(result), 4)
        alice_east = [r for r in result if r["name"] == "Alice" and r["region"] == "East"]
        self.assertEqual(len(alice_east), 1)
        self.assertEqual(alice_east[0]["sales"], 100)

    def test_callbacks(self):
        events = []
        self.pivot.on_change("tracker", lambda action, detail: events.append(action))
        self.pivot.configure_pivot("pipe1", "region", "sales")
        self.assertIn("configure_pivot", events)
        self.assertTrue(self.pivot.remove_callback("tracker"))
        self.assertFalse(self.pivot.remove_callback("tracker"))

    def test_get_stats(self):
        self.pivot.configure_pivot("pipe1", "region", "sales")
        stats = self.pivot.get_stats()
        self.assertEqual(stats["total_configs"], 1)
        self.assertEqual(stats["pipelines"], 1)
        self.assertGreaterEqual(stats["seq"], 1)

    def test_reset(self):
        self.pivot.configure_pivot("pipe1", "region", "sales")
        self.pivot.reset()
        self.assertEqual(self.pivot.get_config_count(), 0)
        self.assertEqual(len(self.pivot.list_pipelines()), 0)

    def test_unique_ids(self):
        id1 = self.pivot.configure_pivot("pipe1", "region", "sales")
        id2 = self.pivot.configure_pivot("pipe1", "region", "sales")
        self.assertNotEqual(id1, id2)

    def test_pivot_with_sum_agg(self):
        self.pivot.configure_pivot("pipe1", "region", "sales", agg="sum")
        records = [
            {"name": "Alice", "region": "East", "sales": 100},
            {"name": "Alice", "region": "East", "sales": 50},
            {"name": "Alice", "region": "West", "sales": 200},
        ]
        result = self.pivot.pivot("pipe1", records)
        alice_row = result[0]
        self.assertEqual(alice_row["East"], 150)
        self.assertEqual(alice_row["West"], 200)

    def test_state_dataclass(self):
        state = PipelineDataPivotState()
        self.assertIsInstance(state.entries, dict)
        self.assertEqual(state._seq, 0)


if __name__ == "__main__":
    unittest.main()
