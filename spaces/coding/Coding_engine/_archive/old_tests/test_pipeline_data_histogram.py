"""Tests for PipelineDataHistogram service."""

import sys
import unittest

sys.path.insert(0, ".")
from src.services.pipeline_data_histogram import PipelineDataHistogram


class TestPipelineDataHistogram(unittest.TestCase):
    def setUp(self):
        self.hist = PipelineDataHistogram()

    def test_create_histogram(self):
        hid = self.hist.create_histogram("pipe-1", "latency")
        self.assertTrue(hid.startswith("pdh-"))
        self.assertEqual(len(hid), 4 + 16)  # "pdh-" + 16 hex chars

    def test_create_histogram_custom_bins(self):
        hid = self.hist.create_histogram("pipe-1", "score", bin_count=5, min_val=0.0, max_val=50.0)
        result = self.hist.get_histogram(hid)
        self.assertEqual(len(result["bins"]), 5)
        self.assertAlmostEqual(result["bins"][0]["low"], 0.0)
        self.assertAlmostEqual(result["bins"][0]["high"], 10.0)

    def test_add_values_and_get_histogram(self):
        hid = self.hist.create_histogram("pipe-1", "latency", bin_count=10, min_val=0.0, max_val=100.0)
        ok = self.hist.add_values(hid, [5, 15, 25, 35, 45, 55, 65, 75, 85, 95])
        self.assertTrue(ok)
        result = self.hist.get_histogram(hid)
        self.assertEqual(result["total"], 10)
        for b in result["bins"]:
            self.assertEqual(b["count"], 1)

    def test_add_values_invalid_histogram(self):
        ok = self.hist.add_values("pdh-nonexistent", [1, 2, 3])
        self.assertFalse(ok)

    def test_add_values_out_of_range(self):
        hid = self.hist.create_histogram("pipe-1", "val", bin_count=5, min_val=0.0, max_val=50.0)
        self.hist.add_values(hid, [-10, 60, 25])
        result = self.hist.get_histogram(hid)
        self.assertEqual(result["total"], 1)  # Only 25 is in range

    def test_add_values_at_max(self):
        hid = self.hist.create_histogram("pipe-1", "val", bin_count=5, min_val=0.0, max_val=50.0)
        self.hist.add_values(hid, [50.0])
        result = self.hist.get_histogram(hid)
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["bins"][-1]["count"], 1)

    def test_get_percentile(self):
        hid = self.hist.create_histogram("pipe-1", "latency", bin_count=10, min_val=0.0, max_val=100.0)
        self.hist.add_values(hid, [5, 15, 25, 35, 45, 55, 65, 75, 85, 95])
        p50 = self.hist.get_percentile(hid, 50)
        self.assertGreater(p50, 40)
        self.assertLess(p50, 60)

    def test_get_percentile_empty(self):
        hid = self.hist.create_histogram("pipe-1", "val")
        p50 = self.hist.get_percentile(hid, 50)
        self.assertEqual(p50, 0.0)

    def test_get_histograms_by_pipeline(self):
        self.hist.create_histogram("pipe-1", "latency")
        self.hist.create_histogram("pipe-1", "throughput")
        self.hist.create_histogram("pipe-2", "latency")
        result = self.hist.get_histograms("pipe-1")
        self.assertEqual(len(result), 2)

    def test_remove_histogram(self):
        hid = self.hist.create_histogram("pipe-1", "latency")
        self.assertTrue(self.hist.remove_histogram(hid))
        self.assertFalse(self.hist.remove_histogram(hid))
        self.assertEqual(self.hist.get_histogram(hid), {})

    def test_get_histogram_count(self):
        self.hist.create_histogram("pipe-1", "a")
        self.hist.create_histogram("pipe-1", "b")
        self.hist.create_histogram("pipe-2", "a")
        self.assertEqual(self.hist.get_histogram_count(), 3)
        self.assertEqual(self.hist.get_histogram_count("pipe-1"), 2)
        self.assertEqual(self.hist.get_histogram_count("pipe-2"), 1)
        self.assertEqual(self.hist.get_histogram_count("pipe-3"), 0)

    def test_list_pipelines(self):
        self.hist.create_histogram("pipe-b", "x")
        self.hist.create_histogram("pipe-a", "y")
        self.hist.create_histogram("pipe-b", "z")
        pipelines = self.hist.list_pipelines()
        self.assertEqual(pipelines, ["pipe-a", "pipe-b"])

    def test_callbacks(self):
        events = []
        cb_id = self.hist.on_change(lambda e, d: events.append((e, d)))
        self.assertTrue(cb_id.startswith("pdh-"))
        self.hist.create_histogram("pipe-1", "val")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "histogram_created")
        self.assertTrue(self.hist.remove_callback(cb_id))
        self.assertFalse(self.hist.remove_callback(cb_id))

    def test_get_stats(self):
        self.hist.create_histogram("pipe-1", "a")
        self.hist.create_histogram("pipe-2", "b")
        stats = self.hist.get_stats()
        self.assertEqual(stats["total_histograms"], 2)
        self.assertEqual(stats["pipelines"], 2)
        self.assertGreater(stats["seq"], 0)

    def test_reset(self):
        self.hist.create_histogram("pipe-1", "a")
        cb_id = self.hist.on_change(lambda e, d: None)
        self.hist.reset()
        self.assertEqual(self.hist.get_histogram_count(), 0)
        self.assertEqual(len(self.hist.callbacks), 0)
        self.assertEqual(self.hist.state._seq, 0)

    def test_get_histogram_not_found(self):
        result = self.hist.get_histogram("pdh-doesnotexist")
        self.assertEqual(result, {})

    def test_get_percentile_not_found(self):
        result = self.hist.get_percentile("pdh-doesnotexist", 50)
        self.assertEqual(result, 0.0)


if __name__ == "__main__":
    unittest.main()
