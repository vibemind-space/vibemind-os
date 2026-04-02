from __future__ import annotations

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.services.pipeline_data_resolver import PipelineDataResolver


class TestBasic(unittest.TestCase):
    def setUp(self):
        self.resolver = PipelineDataResolver()

    def test_returns_id(self):
        rid = self.resolver.resolve("pipe-1", "key-a")
        self.assertTrue(rid.startswith("pdrs-"))

    def test_fields(self):
        rid = self.resolver.resolve("pipe-1", "key-a", strategy="manual")
        entry = self.resolver.get_resolution(rid)
        self.assertEqual(entry["pipeline_id"], "pipe-1")
        self.assertEqual(entry["data_key"], "key-a")
        self.assertEqual(entry["strategy"], "manual")
        self.assertIn("created_at", entry)
        self.assertIn("updated_at", entry)

    def test_default_strategy(self):
        rid = self.resolver.resolve("pipe-1", "key-a")
        entry = self.resolver.get_resolution(rid)
        self.assertEqual(entry["strategy"], "auto")

    def test_metadata_deepcopy(self):
        meta = {"nested": {"value": 1}}
        rid = self.resolver.resolve("pipe-1", "key-a", metadata=meta)
        meta["nested"]["value"] = 999
        entry = self.resolver.get_resolution(rid)
        self.assertEqual(entry["metadata"]["nested"]["value"], 1)

    def test_empty_pipeline(self):
        rid = self.resolver.resolve("", "key-a")
        self.assertEqual(rid, "")

    def test_empty_data_key(self):
        rid = self.resolver.resolve("pipe-1", "")
        self.assertEqual(rid, "")


class TestGet(unittest.TestCase):
    def setUp(self):
        self.resolver = PipelineDataResolver()

    def test_found(self):
        rid = self.resolver.resolve("pipe-1", "key-a")
        entry = self.resolver.get_resolution(rid)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["record_id"], rid)

    def test_not_found(self):
        result = self.resolver.get_resolution("nonexistent")
        self.assertIsNone(result)

    def test_copy(self):
        rid = self.resolver.resolve("pipe-1", "key-a")
        e1 = self.resolver.get_resolution(rid)
        e2 = self.resolver.get_resolution(rid)
        self.assertIsNot(e1, e2)


class TestList(unittest.TestCase):
    def setUp(self):
        self.resolver = PipelineDataResolver()

    def test_all(self):
        self.resolver.resolve("pipe-1", "key-a")
        self.resolver.resolve("pipe-2", "key-b")
        results = self.resolver.get_resolutions()
        self.assertEqual(len(results), 2)

    def test_filter(self):
        self.resolver.resolve("pipe-1", "key-a")
        self.resolver.resolve("pipe-2", "key-b")
        self.resolver.resolve("pipe-1", "key-c")
        results = self.resolver.get_resolutions(pipeline_id="pipe-1")
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r["pipeline_id"], "pipe-1")

    def test_newest_first(self):
        self.resolver.resolve("pipe-1", "key-a")
        self.resolver.resolve("pipe-1", "key-b")
        self.resolver.resolve("pipe-1", "key-c")
        results = self.resolver.get_resolutions()
        seqs = [r["_seq"] for r in results]
        self.assertEqual(seqs, sorted(seqs, reverse=True))


class TestCount(unittest.TestCase):
    def setUp(self):
        self.resolver = PipelineDataResolver()

    def test_total(self):
        self.resolver.resolve("pipe-1", "key-a")
        self.resolver.resolve("pipe-2", "key-b")
        self.assertEqual(self.resolver.get_resolution_count(), 2)

    def test_filtered(self):
        self.resolver.resolve("pipe-1", "key-a")
        self.resolver.resolve("pipe-2", "key-b")
        self.resolver.resolve("pipe-1", "key-c")
        self.assertEqual(self.resolver.get_resolution_count(pipeline_id="pipe-1"), 2)


class TestStats(unittest.TestCase):
    def test_data(self):
        resolver = PipelineDataResolver()
        resolver.resolve("pipe-1", "key-a")
        resolver.resolve("pipe-2", "key-b")
        resolver.resolve("pipe-1", "key-c")
        stats = resolver.get_stats()
        self.assertEqual(stats["total_resolutions"], 3)
        self.assertEqual(stats["unique_pipelines"], 2)


class TestCallbacks(unittest.TestCase):
    def setUp(self):
        self.resolver = PipelineDataResolver()

    def test_on_change(self):
        calls = []
        self.resolver.on_change = lambda action, data: calls.append(action)
        self.resolver.resolve("pipe-1", "key-a")
        self.assertIn("resolve", calls)

    def test_remove_true(self):
        self.resolver._state.callbacks["cb1"] = lambda a, d: None
        self.assertTrue(self.resolver.remove_callback("cb1"))

    def test_registered_callback(self):
        calls = []
        self.resolver._state.callbacks["cb1"] = lambda a, d: calls.append(a)
        self.resolver.resolve("pipe-1", "key-a")
        self.assertIn("resolve", calls)

    def test_remove_false(self):
        self.assertFalse(self.resolver.remove_callback("nonexistent"))


class TestPrune(unittest.TestCase):
    def test_prune(self):
        resolver = PipelineDataResolver()
        resolver.MAX_ENTRIES = 5
        for i in range(7):
            resolver.resolve(f"pipe-{i}", f"key-{i}")
        self.assertLessEqual(resolver.get_resolution_count(), 6)


class TestReset(unittest.TestCase):
    def setUp(self):
        self.resolver = PipelineDataResolver()

    def test_clears(self):
        self.resolver.on_change = lambda a, d: None
        self.resolver.resolve("pipe-1", "key-a")
        self.resolver.reset()
        self.assertEqual(self.resolver.get_resolution_count(), 0)
        self.assertIsNone(self.resolver.on_change)

    def test_seq(self):
        self.resolver.resolve("pipe-1", "key-a")
        self.resolver.reset()
        self.assertEqual(self.resolver._state._seq, 0)


if __name__ == "__main__":
    unittest.main()
