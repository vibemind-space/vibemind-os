"""Tests for PipelineDataAggregatorV2."""

import sys
import unittest

sys.path.insert(0, ".")
from src.services.pipeline_data_aggregator_v2 import PipelineDataAggregatorV2


class TestPipelineDataAggregatorV2(unittest.TestCase):

    def setUp(self):
        self.agg = PipelineDataAggregatorV2()

    # -- aggregate_v2 basics --

    def test_aggregate_v2_returns_id(self):
        rid = self.agg.aggregate_v2("pipe1", "clicks")
        self.assertTrue(rid.startswith("pdav-"))

    def test_aggregate_v2_default_method(self):
        rid = self.agg.aggregate_v2("pipe1", "clicks")
        entry = self.agg.get_aggregation(rid)
        self.assertEqual(entry["method"], "sum")

    def test_aggregate_v2_custom_method(self):
        rid = self.agg.aggregate_v2("pipe1", "latency", method="avg")
        entry = self.agg.get_aggregation(rid)
        self.assertEqual(entry["method"], "avg")

    def test_aggregate_v2_with_metadata(self):
        meta = {"source": "web", "version": 3}
        rid = self.agg.aggregate_v2("pipe1", "clicks", metadata=meta)
        entry = self.agg.get_aggregation(rid)
        self.assertEqual(entry["metadata"]["source"], "web")
        self.assertEqual(entry["metadata"]["version"], 3)

    def test_aggregate_v2_metadata_is_deep_copied(self):
        meta = {"nested": {"key": "val"}}
        rid = self.agg.aggregate_v2("pipe1", "clicks", metadata=meta)
        meta["nested"]["key"] = "changed"
        entry = self.agg.get_aggregation(rid)
        self.assertEqual(entry["metadata"]["nested"]["key"], "val")

    def test_aggregate_v2_empty_pipeline_id(self):
        result = self.agg.aggregate_v2("", "clicks")
        self.assertEqual(result, "")

    def test_aggregate_v2_empty_data_key_or_both(self):
        self.assertEqual(self.agg.aggregate_v2("pipe1", ""), "")
        self.assertEqual(self.agg.aggregate_v2("", ""), "")

    # -- get_aggregation --

    def test_get_aggregation_found(self):
        rid = self.agg.aggregate_v2("pipe1", "clicks")
        entry = self.agg.get_aggregation(rid)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["pipeline_id"], "pipe1")
        self.assertEqual(entry["data_key"], "clicks")

    def test_get_aggregation_not_found(self):
        result = self.agg.get_aggregation("pdav-nonexistent")
        self.assertIsNone(result)

    def test_get_aggregation_returns_copy(self):
        rid = self.agg.aggregate_v2("pipe1", "clicks")
        e1 = self.agg.get_aggregation(rid)
        e2 = self.agg.get_aggregation(rid)
        self.assertEqual(e1, e2)
        self.assertIsNot(e1, e2)

    # -- get_aggregations --

    def test_get_aggregations_all(self):
        self.agg.aggregate_v2("pipe1", "a")
        self.agg.aggregate_v2("pipe2", "b")
        self.agg.aggregate_v2("pipe1", "c")
        results = self.agg.get_aggregations()
        self.assertEqual(len(results), 3)

    def test_get_aggregations_filtered(self):
        self.agg.aggregate_v2("pipe1", "a")
        self.agg.aggregate_v2("pipe2", "b")
        self.agg.aggregate_v2("pipe1", "c")
        results = self.agg.get_aggregations(pipeline_id="pipe1")
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r["pipeline_id"], "pipe1")

    def test_get_aggregations_sorted_reverse(self):
        r1 = self.agg.aggregate_v2("pipe1", "a")
        r2 = self.agg.aggregate_v2("pipe1", "b")
        r3 = self.agg.aggregate_v2("pipe1", "c")
        results = self.agg.get_aggregations(pipeline_id="pipe1")
        ids = [r["record_id"] for r in results]
        self.assertEqual(ids[0], r3)
        self.assertEqual(ids[-1], r1)

    def test_get_aggregations_limit(self):
        for i in range(10):
            self.agg.aggregate_v2("pipe1", f"key{i}")
        results = self.agg.get_aggregations(pipeline_id="pipe1", limit=3)
        self.assertEqual(len(results), 3)

    # -- get_aggregation_count --

    def test_get_aggregation_count(self):
        self.agg.aggregate_v2("pipe1", "a")
        self.agg.aggregate_v2("pipe2", "b")
        self.agg.aggregate_v2("pipe1", "c")
        self.assertEqual(self.agg.get_aggregation_count(), 3)
        self.assertEqual(self.agg.get_aggregation_count("pipe1"), 2)
        self.assertEqual(self.agg.get_aggregation_count("pipe2"), 1)

    # -- get_stats --

    def test_get_stats(self):
        self.agg.aggregate_v2("pipe1", "a")
        self.agg.aggregate_v2("pipe2", "b")
        self.agg.aggregate_v2("pipe1", "c")
        stats = self.agg.get_stats()
        self.assertEqual(stats["total_aggregations"], 3)
        self.assertEqual(stats["unique_pipelines"], 2)

    # -- reset --

    def test_reset_clears_entries(self):
        self.agg.aggregate_v2("pipe1", "a")
        self.agg.on_change("cb1", lambda a, d: None)
        self.agg.reset()
        self.assertEqual(self.agg.get_aggregation_count(), 0)
        self.assertEqual(self.agg.get_stats()["total_aggregations"], 0)

    # -- callbacks --

    def test_on_change_registers(self):
        result = self.agg.on_change("mycb", lambda a, d: None)
        self.assertTrue(result)

    def test_on_change_duplicate_name(self):
        self.agg.on_change("mycb", lambda a, d: None)
        result = self.agg.on_change("mycb", lambda a, d: None)
        self.assertFalse(result)

    def test_callback_fires_on_aggregate(self):
        events = []
        self.agg.on_change("mycb", lambda a, d: events.append((a, d)))
        self.agg.aggregate_v2("pipe1", "clicks")
        self.assertEqual(len(events), 1)
        action, data = events[0]
        self.assertEqual(action, "aggregation_created")
        self.assertEqual(data["action"], "aggregation_created")
        self.assertIn("record_id", data)

    def test_remove_callback(self):
        self.agg.on_change("mycb", lambda a, d: None)
        self.assertTrue(self.agg.remove_callback("mycb"))
        self.assertFalse(self.agg.remove_callback("mycb"))

    # -- MAX_ENTRIES limit --

    def test_max_entries_enforced(self):
        original_max = PipelineDataAggregatorV2.MAX_ENTRIES
        PipelineDataAggregatorV2.MAX_ENTRIES = 3
        try:
            self.agg.aggregate_v2("p", "a")
            self.agg.aggregate_v2("p", "b")
            self.agg.aggregate_v2("p", "c")
            result = self.agg.aggregate_v2("p", "d")
            self.assertEqual(result, "")
            self.assertEqual(self.agg.get_aggregation_count(), 3)
        finally:
            PipelineDataAggregatorV2.MAX_ENTRIES = original_max


if __name__ == "__main__":
    unittest.main()
