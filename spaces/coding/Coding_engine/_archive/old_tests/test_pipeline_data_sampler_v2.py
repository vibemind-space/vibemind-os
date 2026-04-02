"""Tests for PipelineDataSamplerV2."""

import sys
import unittest

sys.path.insert(0, ".")
from src.services.pipeline_data_sampler_v2 import PipelineDataSamplerV2


class TestPipelineDataSamplerV2(unittest.TestCase):

    def setUp(self):
        self.sampler = PipelineDataSamplerV2()

    def test_create_sampler_reservoir(self):
        sid = self.sampler.create_sampler("pipe1", strategy="reservoir", sample_size=50)
        self.assertTrue(sid.startswith("pds2-"))
        info = self.sampler.get_sampler(sid)
        self.assertEqual(info["pipeline_id"], "pipe1")
        self.assertEqual(info["strategy"], "reservoir")
        self.assertEqual(info["sample_size"], 50)

    def test_create_sampler_invalid_strategy(self):
        with self.assertRaises(ValueError):
            self.sampler.create_sampler("pipe1", strategy="invalid")

    def test_add_record_reservoir(self):
        sid = self.sampler.create_sampler("pipe1", strategy="reservoir", sample_size=5)
        for i in range(5):
            result = self.sampler.add_record(sid, {"val": i})
            self.assertTrue(result)
        self.assertEqual(self.sampler.get_sample_size(sid), 5)

    def test_reservoir_sampling_overflow(self):
        sid = self.sampler.create_sampler("pipe1", strategy="reservoir", sample_size=3)
        for i in range(100):
            self.sampler.add_record(sid, {"val": i})
        self.assertEqual(self.sampler.get_sample_size(sid), 3)

    def test_get_sample_returns_copy(self):
        sid = self.sampler.create_sampler("pipe1", sample_size=10)
        self.sampler.add_record(sid, {"x": 1})
        s1 = self.sampler.get_sample(sid)
        s2 = self.sampler.get_sample(sid)
        self.assertEqual(s1, s2)
        self.assertIsNot(s1, s2)

    def test_stratified_sampling(self):
        sid = self.sampler.create_sampler("pipe1", strategy="stratified", sample_size=10)
        self.sampler.configure_strata(sid, "category", {"A": 3, "B": 3})
        for i in range(10):
            cat = "A" if i % 2 == 0 else "B"
            self.sampler.add_record(sid, {"category": cat, "val": i})
        sample = self.sampler.get_sample(sid)
        self.assertGreater(len(sample), 0)

    def test_systematic_sampling(self):
        sid = self.sampler.create_sampler("pipe1", strategy="systematic", sample_size=5)
        for i in range(20):
            self.sampler.add_record(sid, {"val": i})
        size = self.sampler.get_sample_size(sid)
        self.assertGreater(size, 0)
        self.assertLessEqual(size, 5)

    def test_get_sampler_not_found(self):
        result = self.sampler.get_sampler("pds2-nonexistent")
        self.assertIsNone(result)

    def test_get_samplers_by_pipeline(self):
        self.sampler.create_sampler("pipe1")
        self.sampler.create_sampler("pipe1")
        self.sampler.create_sampler("pipe2")
        self.assertEqual(len(self.sampler.get_samplers("pipe1")), 2)
        self.assertEqual(len(self.sampler.get_samplers("pipe2")), 1)

    def test_get_sampler_count(self):
        self.sampler.create_sampler("pipe1")
        self.sampler.create_sampler("pipe2")
        self.assertEqual(self.sampler.get_sampler_count(), 2)
        self.assertEqual(self.sampler.get_sampler_count("pipe1"), 1)

    def test_list_pipelines(self):
        self.sampler.create_sampler("alpha")
        self.sampler.create_sampler("beta")
        self.sampler.create_sampler("alpha")
        pipelines = self.sampler.list_pipelines()
        self.assertEqual(sorted(pipelines), ["alpha", "beta"])

    def test_callbacks(self):
        events = []
        cb_id = self.sampler.on_change(lambda e, d: events.append(e))
        self.assertTrue(cb_id.startswith("pds2-"))
        sid = self.sampler.create_sampler("pipe1")
        self.assertIn("sampler_created", events)
        self.sampler.add_record(sid, {"x": 1})
        self.assertIn("record_added", events)
        self.assertTrue(self.sampler.remove_callback(cb_id))
        self.assertFalse(self.sampler.remove_callback(cb_id))

    def test_get_stats(self):
        sid = self.sampler.create_sampler("pipe1")
        for i in range(5):
            self.sampler.add_record(sid, {"v": i})
        stats = self.sampler.get_stats()
        self.assertEqual(stats["sampler_count"], 1)
        self.assertEqual(stats["pipeline_count"], 1)
        self.assertEqual(stats["total_records_seen"], 5)
        self.assertGreaterEqual(stats["total_sampled"], 1)

    def test_reset(self):
        self.sampler.create_sampler("pipe1")
        self.sampler.on_change(lambda e, d: None)
        self.sampler.reset()
        self.assertEqual(self.sampler.get_sampler_count(), 0)
        self.assertEqual(self.sampler.get_stats()["callback_count"], 0)

    def test_configure_strata_not_found(self):
        result = self.sampler.configure_strata("pds2-missing", "field")
        self.assertFalse(result)

    def test_add_record_not_found(self):
        with self.assertRaises(KeyError):
            self.sampler.add_record("pds2-missing", {"x": 1})


if __name__ == "__main__":
    unittest.main()
