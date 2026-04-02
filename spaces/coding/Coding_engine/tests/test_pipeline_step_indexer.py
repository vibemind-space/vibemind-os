"""Tests for pipeline_step_indexer service."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_step_indexer import PipelineStepIndexer


class TestBasic(unittest.TestCase):
    """Basic indexing tests."""

    def setUp(self) -> None:
        self.indexer = PipelineStepIndexer()

    def test_prefix(self) -> None:
        rid = self.indexer.index("p1", "step1")
        self.assertTrue(rid.startswith("psix-"))

    def test_fields_present(self) -> None:
        rid = self.indexer.index("p1", "step1")
        rec = self.indexer.get_index(rid)
        self.assertIsNotNone(rec)
        for key in ("record_id", "pipeline_id", "step_name", "index_type",
                     "metadata", "created_at", "updated_at", "_seq"):
            self.assertIn(key, rec)

    def test_default_index_type_is_primary(self) -> None:
        rid = self.indexer.index("p1", "step1")
        rec = self.indexer.get_index(rid)
        self.assertEqual(rec["index_type"], "primary")

    def test_custom_index_type(self) -> None:
        rid = self.indexer.index("p1", "step1", index_type="secondary")
        rec = self.indexer.get_index(rid)
        self.assertEqual(rec["index_type"], "secondary")

    def test_metadata_deepcopy(self) -> None:
        meta = {"nested": {"a": 1}}
        rid = self.indexer.index("p1", "step1", metadata=meta)
        meta["nested"]["a"] = 999
        rec = self.indexer.get_index(rid)
        self.assertEqual(rec["metadata"]["nested"]["a"], 1)

    def test_empty_pipeline_id_returns_empty(self) -> None:
        result = self.indexer.index("", "step1")
        self.assertEqual(result, "")

    def test_empty_step_name_returns_empty(self) -> None:
        result = self.indexer.index("p1", "")
        self.assertEqual(result, "")

    def test_unique_ids(self) -> None:
        ids = {self.indexer.index("p1", f"s{i}") for i in range(10)}
        self.assertEqual(len(ids), 10)


class TestGet(unittest.TestCase):
    """Tests for get_index."""

    def setUp(self) -> None:
        self.indexer = PipelineStepIndexer()

    def test_get_existing(self) -> None:
        rid = self.indexer.index("p1", "step1")
        rec = self.indexer.get_index(rid)
        self.assertEqual(rec["record_id"], rid)

    def test_get_nonexistent_returns_none(self) -> None:
        self.assertIsNone(self.indexer.get_index("psix-doesnotexist"))

    def test_get_returns_copy(self) -> None:
        rid = self.indexer.index("p1", "step1")
        rec1 = self.indexer.get_index(rid)
        rec1["pipeline_id"] = "modified"
        rec2 = self.indexer.get_index(rid)
        self.assertEqual(rec2["pipeline_id"], "p1")


class TestList(unittest.TestCase):
    """Tests for get_indexes."""

    def setUp(self) -> None:
        self.indexer = PipelineStepIndexer()

    def test_list_all(self) -> None:
        self.indexer.index("p1", "s1")
        self.indexer.index("p2", "s2")
        results = self.indexer.get_indexes()
        self.assertEqual(len(results), 2)

    def test_list_filtered(self) -> None:
        self.indexer.index("p1", "s1")
        self.indexer.index("p2", "s2")
        self.indexer.index("p1", "s3")
        results = self.indexer.get_indexes(pipeline_id="p1")
        self.assertEqual(len(results), 2)

    def test_list_newest_first(self) -> None:
        r1 = self.indexer.index("p1", "s1")
        r2 = self.indexer.index("p1", "s2")
        results = self.indexer.get_indexes()
        self.assertEqual(results[0]["record_id"], r2)
        self.assertEqual(results[1]["record_id"], r1)

    def test_list_with_limit(self) -> None:
        for i in range(10):
            self.indexer.index("p1", f"s{i}")
        results = self.indexer.get_indexes(limit=3)
        self.assertEqual(len(results), 3)


class TestCount(unittest.TestCase):
    """Tests for get_index_count."""

    def setUp(self) -> None:
        self.indexer = PipelineStepIndexer()

    def test_count_all(self) -> None:
        self.indexer.index("p1", "s1")
        self.indexer.index("p2", "s2")
        self.assertEqual(self.indexer.get_index_count(), 2)

    def test_count_filtered(self) -> None:
        self.indexer.index("p1", "s1")
        self.indexer.index("p2", "s2")
        self.indexer.index("p1", "s3")
        self.assertEqual(self.indexer.get_index_count(pipeline_id="p1"), 2)


class TestStats(unittest.TestCase):
    """Tests for get_stats."""

    def setUp(self) -> None:
        self.indexer = PipelineStepIndexer()

    def test_stats_empty(self) -> None:
        stats = self.indexer.get_stats()
        self.assertEqual(stats["total_indexes"], 0)
        self.assertEqual(stats["unique_pipelines"], 0)

    def test_stats_populated(self) -> None:
        self.indexer.index("p1", "s1")
        self.indexer.index("p2", "s2")
        self.indexer.index("p1", "s3")
        stats = self.indexer.get_stats()
        self.assertEqual(stats["total_indexes"], 3)
        self.assertEqual(stats["unique_pipelines"], 2)


class TestCallbacks(unittest.TestCase):
    """Tests for callback system."""

    def setUp(self) -> None:
        self.indexer = PipelineStepIndexer()

    def test_on_change_fires(self) -> None:
        calls = []
        self.indexer.on_change = lambda action, **kw: calls.append((action, kw))
        self.indexer.index("p1", "s1")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "index")

    def test_on_change_property(self) -> None:
        self.assertIsNone(self.indexer.on_change)
        fn = lambda a, **kw: None
        self.indexer.on_change = fn
        self.assertIs(self.indexer.on_change, fn)

    def test_registered_callback_fires(self) -> None:
        calls = []
        self.indexer._state.callbacks["cb1"] = lambda action, **kw: calls.append(action)
        self.indexer.index("p1", "s1")
        self.assertEqual(calls, ["index"])

    def test_remove_callback(self) -> None:
        self.indexer._state.callbacks["cb1"] = lambda a, **kw: None
        self.assertTrue(self.indexer.remove_callback("cb1"))
        self.assertFalse(self.indexer.remove_callback("cb1"))

    def test_callback_error_does_not_propagate(self) -> None:
        def bad_cb(action, **kw):
            raise RuntimeError("boom")
        self.indexer.on_change = bad_cb
        rid = self.indexer.index("p1", "s1")
        self.assertTrue(rid.startswith("psix-"))


class TestPrune(unittest.TestCase):
    """Tests for pruning."""

    def setUp(self) -> None:
        self.indexer = PipelineStepIndexer()
        self.indexer.MAX_ENTRIES = 5

    def test_prune_removes_oldest_quarter(self) -> None:
        for i in range(7):
            self.indexer.index("p1", f"s{i}")
        # After adding 6th entry (>5), prune fires: removes 6//4=1 entry
        # After adding 7th entry (>5 again), prune fires again
        self.assertLessEqual(len(self.indexer._state.entries), 7)
        # At least some entries were pruned
        self.assertLess(self.indexer.get_index_count(), 7)


class TestReset(unittest.TestCase):
    """Tests for reset."""

    def setUp(self) -> None:
        self.indexer = PipelineStepIndexer()

    def test_reset_clears_entries(self) -> None:
        self.indexer.index("p1", "s1")
        self.indexer.index("p2", "s2")
        self.indexer.reset()
        self.assertEqual(self.indexer.get_index_count(), 0)

    def test_reset_clears_on_change(self) -> None:
        self.indexer.on_change = lambda a, **kw: None
        self.indexer.reset()
        self.assertIsNone(self.indexer.on_change)

    def test_reset_clears_callbacks(self) -> None:
        self.indexer._state.callbacks["cb1"] = lambda a, **kw: None
        self.indexer.reset()
        self.assertEqual(len(self.indexer._state.callbacks), 0)


if __name__ == "__main__":
    unittest.main()
