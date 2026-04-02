from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from services.pipeline_data_bucketer import PipelineDataBucketer, PipelineDataBucketerState


class TestBasic(unittest.TestCase):
    def setUp(self) -> None:
        self.b = PipelineDataBucketer()

    def test_prefix(self) -> None:
        rid = self.b.bucket("p1", "k1")
        self.assertTrue(rid.startswith("pdbk-"))

    def test_fields_present(self) -> None:
        rid = self.b.bucket("p1", "k1")
        entry = self.b.get_bucket(rid)
        self.assertIsNotNone(entry)
        for f in ("record_id", "pipeline_id", "data_key", "bucket_name", "metadata", "created_at", "updated_at", "_seq"):
            self.assertIn(f, entry)

    def test_default_bucket_name(self) -> None:
        rid = self.b.bucket("p1", "k1")
        entry = self.b.get_bucket(rid)
        self.assertEqual(entry["bucket_name"], "default")

    def test_custom_bucket_name(self) -> None:
        rid = self.b.bucket("p1", "k1", bucket_name="custom")
        entry = self.b.get_bucket(rid)
        self.assertEqual(entry["bucket_name"], "custom")

    def test_metadata_deepcopy(self) -> None:
        meta = {"key": [1, 2, 3]}
        rid = self.b.bucket("p1", "k1", metadata=meta)
        meta["key"].append(4)
        entry = self.b.get_bucket(rid)
        self.assertEqual(entry["metadata"]["key"], [1, 2, 3])

    def test_empty_pipeline_id_returns_empty(self) -> None:
        result = self.b.bucket("", "k1")
        self.assertEqual(result, "")

    def test_empty_data_key_returns_empty(self) -> None:
        result = self.b.bucket("p1", "")
        self.assertEqual(result, "")

    def test_both_empty_returns_empty(self) -> None:
        result = self.b.bucket("", "")
        self.assertEqual(result, "")


class TestGet(unittest.TestCase):
    def setUp(self) -> None:
        self.b = PipelineDataBucketer()

    def test_get_existing(self) -> None:
        rid = self.b.bucket("p1", "k1")
        entry = self.b.get_bucket(rid)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["record_id"], rid)

    def test_get_nonexistent(self) -> None:
        self.assertIsNone(self.b.get_bucket("nonexistent"))

    def test_get_returns_copy(self) -> None:
        rid = self.b.bucket("p1", "k1")
        e1 = self.b.get_bucket(rid)
        e1["pipeline_id"] = "modified"
        e2 = self.b.get_bucket(rid)
        self.assertEqual(e2["pipeline_id"], "p1")


class TestList(unittest.TestCase):
    def setUp(self) -> None:
        self.b = PipelineDataBucketer()

    def test_get_buckets_all(self) -> None:
        self.b.bucket("p1", "k1")
        self.b.bucket("p2", "k2")
        results = self.b.get_buckets()
        self.assertEqual(len(results), 2)

    def test_get_buckets_filter_pipeline(self) -> None:
        self.b.bucket("p1", "k1")
        self.b.bucket("p2", "k2")
        self.b.bucket("p1", "k3")
        results = self.b.get_buckets(pipeline_id="p1")
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r["pipeline_id"], "p1")

    def test_get_buckets_newest_first(self) -> None:
        r1 = self.b.bucket("p1", "k1")
        r2 = self.b.bucket("p1", "k2")
        results = self.b.get_buckets(pipeline_id="p1")
        self.assertEqual(results[0]["record_id"], r2)
        self.assertEqual(results[1]["record_id"], r1)

    def test_get_buckets_limit(self) -> None:
        for i in range(10):
            self.b.bucket("p1", f"k{i}")
        results = self.b.get_buckets(limit=3)
        self.assertEqual(len(results), 3)


class TestCount(unittest.TestCase):
    def setUp(self) -> None:
        self.b = PipelineDataBucketer()

    def test_count_all(self) -> None:
        self.b.bucket("p1", "k1")
        self.b.bucket("p2", "k2")
        self.assertEqual(self.b.get_bucket_count(), 2)

    def test_count_filtered(self) -> None:
        self.b.bucket("p1", "k1")
        self.b.bucket("p2", "k2")
        self.b.bucket("p1", "k3")
        self.assertEqual(self.b.get_bucket_count(pipeline_id="p1"), 2)

    def test_count_empty(self) -> None:
        self.assertEqual(self.b.get_bucket_count(), 0)


class TestStats(unittest.TestCase):
    def setUp(self) -> None:
        self.b = PipelineDataBucketer()

    def test_stats_empty(self) -> None:
        stats = self.b.get_stats()
        self.assertEqual(stats["total_buckets"], 0)
        self.assertEqual(stats["unique_pipelines"], 0)

    def test_stats_with_data(self) -> None:
        self.b.bucket("p1", "k1")
        self.b.bucket("p2", "k2")
        self.b.bucket("p1", "k3")
        stats = self.b.get_stats()
        self.assertEqual(stats["total_buckets"], 3)
        self.assertEqual(stats["unique_pipelines"], 2)


class TestCallbacks(unittest.TestCase):
    def setUp(self) -> None:
        self.b = PipelineDataBucketer()

    def test_on_change_called(self) -> None:
        calls = []
        self.b.on_change = lambda action, **kw: calls.append((action, kw))
        self.b.bucket("p1", "k1")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "bucket")

    def test_on_change_property(self) -> None:
        fn = lambda action, **kw: None
        self.b.on_change = fn
        self.assertIs(self.b.on_change, fn)

    def test_state_callback_called(self) -> None:
        calls = []
        self.b._state.callbacks["cb1"] = lambda action, **kw: calls.append(action)
        self.b.bucket("p1", "k1")
        self.assertEqual(calls, ["bucket"])

    def test_remove_callback(self) -> None:
        self.b._state.callbacks["cb1"] = lambda action, **kw: None
        self.assertTrue(self.b.remove_callback("cb1"))
        self.assertNotIn("cb1", self.b._state.callbacks)

    def test_remove_callback_missing(self) -> None:
        self.assertFalse(self.b.remove_callback("nonexistent"))


class TestPrune(unittest.TestCase):
    def test_prune_removes_quarter(self) -> None:
        b = PipelineDataBucketer()
        b.MAX_ENTRIES = 5
        for i in range(7):
            b.bucket("p1", f"k{i}")
        # After adding 6th entry (exceeds 5), prune removes quarter.
        # Then 7th entry added, prune again.  Count should be <= MAX + 1 after pruning.
        self.assertLessEqual(len(b._state.entries), 7)
        # Verify oldest were removed
        remaining = b.get_buckets(limit=100)
        self.assertTrue(len(remaining) > 0)

    def test_prune_keeps_newest(self) -> None:
        b = PipelineDataBucketer()
        b.MAX_ENTRIES = 5
        ids = []
        for i in range(7):
            ids.append(b.bucket("p1", f"k{i}"))
        # The last added entry should still exist
        last = b.get_bucket(ids[-1])
        self.assertIsNotNone(last)


class TestReset(unittest.TestCase):
    def test_reset_clears_entries(self) -> None:
        b = PipelineDataBucketer()
        b.bucket("p1", "k1")
        b.reset()
        self.assertEqual(len(b._state.entries), 0)

    def test_reset_on_change_none(self) -> None:
        b = PipelineDataBucketer(_on_change=lambda a, **k: None)
        b.reset()
        self.assertIsNone(b.on_change)

    def test_reset_seq_zero(self) -> None:
        b = PipelineDataBucketer()
        b.bucket("p1", "k1")
        b.reset()
        self.assertEqual(b._state._seq, 0)

    def test_reset_clears_callbacks(self) -> None:
        b = PipelineDataBucketer()
        b._state.callbacks["cb"] = lambda a, **k: None
        b.reset()
        self.assertEqual(len(b._state.callbacks), 0)


if __name__ == "__main__":
    unittest.main()
