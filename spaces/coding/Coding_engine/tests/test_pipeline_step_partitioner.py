from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from src.services.pipeline_step_partitioner import (
    PipelineStepPartitioner,
    PipelineStepPartitionerState,
)


class TestBasic(unittest.TestCase):
    def setUp(self) -> None:
        self.p = PipelineStepPartitioner()

    def test_prefix(self) -> None:
        rid = self.p.partition("pipe-1", "step-a")
        self.assertTrue(rid.startswith("pspt-"))

    def test_fields_present(self) -> None:
        rid = self.p.partition("pipe-1", "step-a")
        entry = self.p.get_partition(rid)
        self.assertIsNotNone(entry)
        for key in ("record_id", "pipeline_id", "step_name", "partitions",
                     "metadata", "created_at", "updated_at", "_seq"):
            self.assertIn(key, entry)

    def test_default_partitions_is_one(self) -> None:
        rid = self.p.partition("pipe-1", "step-a")
        entry = self.p.get_partition(rid)
        self.assertEqual(entry["partitions"], 1)

    def test_custom_partitions(self) -> None:
        rid = self.p.partition("pipe-1", "step-a", partitions=4)
        entry = self.p.get_partition(rid)
        self.assertEqual(entry["partitions"], 4)

    def test_metadata_deepcopy(self) -> None:
        meta = {"key": [1, 2, 3]}
        rid = self.p.partition("pipe-1", "step-a", metadata=meta)
        meta["key"].append(999)
        entry = self.p.get_partition(rid)
        self.assertNotIn(999, entry["metadata"]["key"])

    def test_empty_pipeline_id_returns_empty(self) -> None:
        result = self.p.partition("", "step-a")
        self.assertEqual(result, "")

    def test_empty_step_name_returns_empty(self) -> None:
        result = self.p.partition("pipe-1", "")
        self.assertEqual(result, "")

    def test_both_empty_returns_empty(self) -> None:
        result = self.p.partition("", "")
        self.assertEqual(result, "")


class TestGet(unittest.TestCase):
    def setUp(self) -> None:
        self.p = PipelineStepPartitioner()

    def test_get_existing(self) -> None:
        rid = self.p.partition("pipe-1", "step-a")
        entry = self.p.get_partition(rid)
        self.assertEqual(entry["record_id"], rid)

    def test_get_nonexistent_returns_none(self) -> None:
        self.assertIsNone(self.p.get_partition("pspt-doesnotexist"))

    def test_get_returns_copy(self) -> None:
        rid = self.p.partition("pipe-1", "step-a")
        e1 = self.p.get_partition(rid)
        e1["pipeline_id"] = "mutated"
        e2 = self.p.get_partition(rid)
        self.assertEqual(e2["pipeline_id"], "pipe-1")


class TestList(unittest.TestCase):
    def setUp(self) -> None:
        self.p = PipelineStepPartitioner()

    def test_list_all(self) -> None:
        self.p.partition("pipe-1", "step-a")
        self.p.partition("pipe-2", "step-b")
        result = self.p.get_partitions()
        self.assertEqual(len(result), 2)

    def test_list_filtered(self) -> None:
        self.p.partition("pipe-1", "step-a")
        self.p.partition("pipe-2", "step-b")
        self.p.partition("pipe-1", "step-c")
        result = self.p.get_partitions(pipeline_id="pipe-1")
        self.assertEqual(len(result), 2)
        for e in result:
            self.assertEqual(e["pipeline_id"], "pipe-1")

    def test_list_newest_first(self) -> None:
        r1 = self.p.partition("pipe-1", "step-a")
        r2 = self.p.partition("pipe-1", "step-b")
        result = self.p.get_partitions(pipeline_id="pipe-1")
        self.assertEqual(result[0]["record_id"], r2)
        self.assertEqual(result[1]["record_id"], r1)

    def test_list_limit(self) -> None:
        for i in range(10):
            self.p.partition("pipe-1", f"step-{i}")
        result = self.p.get_partitions(limit=3)
        self.assertEqual(len(result), 3)


class TestCount(unittest.TestCase):
    def setUp(self) -> None:
        self.p = PipelineStepPartitioner()

    def test_count_all(self) -> None:
        self.p.partition("pipe-1", "step-a")
        self.p.partition("pipe-2", "step-b")
        self.assertEqual(self.p.get_partition_count(), 2)

    def test_count_filtered(self) -> None:
        self.p.partition("pipe-1", "step-a")
        self.p.partition("pipe-2", "step-b")
        self.p.partition("pipe-1", "step-c")
        self.assertEqual(self.p.get_partition_count(pipeline_id="pipe-1"), 2)


class TestStats(unittest.TestCase):
    def test_stats(self) -> None:
        p = PipelineStepPartitioner()
        p.partition("pipe-1", "step-a")
        p.partition("pipe-2", "step-b")
        p.partition("pipe-1", "step-c")
        stats = p.get_stats()
        self.assertEqual(stats["total_partitions"], 3)
        self.assertEqual(stats["unique_pipelines"], 2)

    def test_stats_empty(self) -> None:
        p = PipelineStepPartitioner()
        stats = p.get_stats()
        self.assertEqual(stats["total_partitions"], 0)
        self.assertEqual(stats["unique_pipelines"], 0)


class TestCallbacks(unittest.TestCase):
    def test_on_change_called(self) -> None:
        calls = []
        p = PipelineStepPartitioner(_on_change=lambda action, **kw: calls.append((action, kw)))
        p.partition("pipe-1", "step-a")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "partition")

    def test_on_change_setter(self) -> None:
        calls = []
        p = PipelineStepPartitioner()
        p.on_change = lambda action, **kw: calls.append(action)
        p.partition("pipe-1", "step-a")
        self.assertEqual(calls, ["partition"])

    def test_on_change_property(self) -> None:
        fn = lambda action, **kw: None
        p = PipelineStepPartitioner(_on_change=fn)
        self.assertIs(p.on_change, fn)

    def test_state_callbacks_fired(self) -> None:
        calls = []
        p = PipelineStepPartitioner()
        p._state.callbacks["my_cb"] = lambda action, **kw: calls.append(action)
        p.partition("pipe-1", "step-a")
        self.assertEqual(calls, ["partition"])

    def test_remove_callback(self) -> None:
        p = PipelineStepPartitioner()
        p._state.callbacks["my_cb"] = lambda action, **kw: None
        self.assertTrue(p.remove_callback("my_cb"))
        self.assertFalse(p.remove_callback("my_cb"))

    def test_callback_error_does_not_propagate(self) -> None:
        def bad_cb(action, **kw):
            raise RuntimeError("boom")
        p = PipelineStepPartitioner(_on_change=bad_cb)
        # Should not raise
        rid = p.partition("pipe-1", "step-a")
        self.assertTrue(rid.startswith("pspt-"))


class TestPrune(unittest.TestCase):
    def test_prune_removes_quarter(self) -> None:
        p = PipelineStepPartitioner()
        p.MAX_ENTRIES = 5
        for i in range(7):
            p.partition(f"pipe-{i}", f"step-{i}")
        # After adding 6th entry (exceeds 5), prune removes 6//4=1; after 7th, 7//4=1 again
        # Final count should be <= MAX_ENTRIES + 1 (prune happens after insert)
        self.assertLessEqual(len(p._state.entries), 7)
        # At least some were pruned
        self.assertLess(len(p._state.entries), 7)

    def test_prune_keeps_newest(self) -> None:
        p = PipelineStepPartitioner()
        p.MAX_ENTRIES = 5
        ids = []
        for i in range(7):
            ids.append(p.partition(f"pipe-{i}", f"step-{i}"))
        # The last created entry should still be present
        self.assertIsNotNone(p.get_partition(ids[-1]))


class TestReset(unittest.TestCase):
    def test_reset_clears_entries(self) -> None:
        p = PipelineStepPartitioner()
        p.partition("pipe-1", "step-a")
        p.reset()
        self.assertEqual(p.get_partition_count(), 0)

    def test_reset_clears_on_change(self) -> None:
        p = PipelineStepPartitioner(_on_change=lambda a, **k: None)
        p.reset()
        self.assertIsNone(p.on_change)

    def test_reset_fresh_state(self) -> None:
        p = PipelineStepPartitioner()
        p.partition("pipe-1", "step-a")
        p._state.callbacks["x"] = lambda a, **k: None
        p.reset()
        self.assertEqual(len(p._state.callbacks), 0)
        self.assertEqual(p._state._seq, 0)


if __name__ == "__main__":
    unittest.main()
