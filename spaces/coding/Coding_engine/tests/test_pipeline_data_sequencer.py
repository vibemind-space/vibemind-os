from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from services.pipeline_data_sequencer import PipelineDataSequencer


class TestBasic(unittest.TestCase):
    def setUp(self) -> None:
        self.seq = PipelineDataSequencer()

    def test_prefix(self) -> None:
        rid = self.seq.sequence("pipe1", "key1")
        self.assertTrue(rid.startswith("pdsq-"))

    def test_fields_present(self) -> None:
        rid = self.seq.sequence("pipe1", "key1", order=5, metadata={"x": 1})
        entry = self.seq.get_sequence(rid)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["record_id"], rid)
        self.assertEqual(entry["pipeline_id"], "pipe1")
        self.assertEqual(entry["data_key"], "key1")
        self.assertEqual(entry["order"], 5)
        self.assertEqual(entry["metadata"], {"x": 1})
        self.assertIn("created_at", entry)
        self.assertIn("updated_at", entry)
        self.assertIn("_seq", entry)

    def test_default_order_is_zero(self) -> None:
        rid = self.seq.sequence("pipe1", "key1")
        entry = self.seq.get_sequence(rid)
        self.assertEqual(entry["order"], 0)

    def test_metadata_deepcopy(self) -> None:
        meta = {"nested": [1, 2, 3]}
        rid = self.seq.sequence("pipe1", "key1", metadata=meta)
        meta["nested"].append(4)
        entry = self.seq.get_sequence(rid)
        self.assertEqual(entry["metadata"]["nested"], [1, 2, 3])

    def test_empty_pipeline_id_returns_empty(self) -> None:
        result = self.seq.sequence("", "key1")
        self.assertEqual(result, "")

    def test_empty_data_key_returns_empty(self) -> None:
        result = self.seq.sequence("pipe1", "")
        self.assertEqual(result, "")

    def test_both_empty_returns_empty(self) -> None:
        result = self.seq.sequence("", "")
        self.assertEqual(result, "")


class TestGet(unittest.TestCase):
    def setUp(self) -> None:
        self.seq = PipelineDataSequencer()

    def test_get_existing(self) -> None:
        rid = self.seq.sequence("pipe1", "key1")
        entry = self.seq.get_sequence(rid)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["record_id"], rid)

    def test_get_nonexistent_returns_none(self) -> None:
        self.assertIsNone(self.seq.get_sequence("pdsq-doesnotexist"))

    def test_get_returns_copy(self) -> None:
        rid = self.seq.sequence("pipe1", "key1")
        entry1 = self.seq.get_sequence(rid)
        entry1["pipeline_id"] = "modified"
        entry2 = self.seq.get_sequence(rid)
        self.assertEqual(entry2["pipeline_id"], "pipe1")


class TestList(unittest.TestCase):
    def setUp(self) -> None:
        self.seq = PipelineDataSequencer()

    def test_list_all(self) -> None:
        self.seq.sequence("pipe1", "k1")
        self.seq.sequence("pipe2", "k2")
        results = self.seq.get_sequences()
        self.assertEqual(len(results), 2)

    def test_list_filter_by_pipeline(self) -> None:
        self.seq.sequence("pipe1", "k1")
        self.seq.sequence("pipe2", "k2")
        self.seq.sequence("pipe1", "k3")
        results = self.seq.get_sequences(pipeline_id="pipe1")
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r["pipeline_id"], "pipe1")

    def test_list_sorted_newest_first(self) -> None:
        r1 = self.seq.sequence("pipe1", "k1")
        r2 = self.seq.sequence("pipe1", "k2")
        r3 = self.seq.sequence("pipe1", "k3")
        results = self.seq.get_sequences(pipeline_id="pipe1")
        self.assertEqual(results[0]["record_id"], r3)
        self.assertEqual(results[-1]["record_id"], r1)

    def test_list_respects_limit(self) -> None:
        for i in range(10):
            self.seq.sequence("pipe1", f"k{i}")
        results = self.seq.get_sequences(limit=3)
        self.assertEqual(len(results), 3)


class TestCount(unittest.TestCase):
    def setUp(self) -> None:
        self.seq = PipelineDataSequencer()

    def test_count_all(self) -> None:
        self.seq.sequence("pipe1", "k1")
        self.seq.sequence("pipe2", "k2")
        self.assertEqual(self.seq.get_sequence_count(), 2)

    def test_count_by_pipeline(self) -> None:
        self.seq.sequence("pipe1", "k1")
        self.seq.sequence("pipe2", "k2")
        self.seq.sequence("pipe1", "k3")
        self.assertEqual(self.seq.get_sequence_count(pipeline_id="pipe1"), 2)
        self.assertEqual(self.seq.get_sequence_count(pipeline_id="pipe2"), 1)

    def test_count_empty(self) -> None:
        self.assertEqual(self.seq.get_sequence_count(), 0)


class TestStats(unittest.TestCase):
    def setUp(self) -> None:
        self.seq = PipelineDataSequencer()

    def test_stats_structure(self) -> None:
        stats = self.seq.get_stats()
        self.assertIn("total_sequences", stats)
        self.assertIn("unique_pipelines", stats)

    def test_stats_values(self) -> None:
        self.seq.sequence("pipe1", "k1")
        self.seq.sequence("pipe2", "k2")
        self.seq.sequence("pipe1", "k3")
        stats = self.seq.get_stats()
        self.assertEqual(stats["total_sequences"], 3)
        self.assertEqual(stats["unique_pipelines"], 2)


class TestCallbacks(unittest.TestCase):
    def setUp(self) -> None:
        self.seq = PipelineDataSequencer()

    def test_on_change_property(self) -> None:
        self.assertIsNone(self.seq.on_change)
        cb = lambda action, **kw: None
        self.seq.on_change = cb
        self.assertIs(self.seq.on_change, cb)

    def test_on_change_fires(self) -> None:
        calls = []
        self.seq.on_change = lambda action, **kw: calls.append((action, kw))
        self.seq.sequence("pipe1", "key1")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "sequence")

    def test_state_callback_fires(self) -> None:
        calls = []
        self.seq._state.callbacks["test_cb"] = lambda action, **kw: calls.append(action)
        self.seq.sequence("pipe1", "key1")
        self.assertIn("sequence", calls)

    def test_remove_callback_existing(self) -> None:
        self.seq._state.callbacks["cb1"] = lambda action, **kw: None
        self.assertTrue(self.seq.remove_callback("cb1"))
        self.assertNotIn("cb1", self.seq._state.callbacks)

    def test_remove_callback_nonexistent(self) -> None:
        self.assertFalse(self.seq.remove_callback("nope"))


class TestPrune(unittest.TestCase):
    def test_prune_removes_oldest_quarter(self) -> None:
        seq = PipelineDataSequencer()
        seq.MAX_ENTRIES = 5
        for i in range(7):
            seq.sequence("pipe1", f"k{i}")
        # After adding 6th entry (exceeds 5), prune removes 6//4=1.
        # After adding 7th entry (6 > 5), prune removes 6//4=1 again.
        # Net: 7 added, some pruned. Should be <= MAX_ENTRIES + 1
        self.assertLessEqual(len(seq._state.entries), 7)
        # Verify it actually pruned (should be less than 7)
        self.assertLess(len(seq._state.entries), 7)


class TestReset(unittest.TestCase):
    def setUp(self) -> None:
        self.seq = PipelineDataSequencer()

    def test_reset_clears_entries(self) -> None:
        self.seq.sequence("pipe1", "k1")
        self.seq.sequence("pipe2", "k2")
        self.seq.reset()
        self.assertEqual(len(self.seq._state.entries), 0)

    def test_reset_on_change_is_none(self) -> None:
        self.seq.on_change = lambda action, **kw: None
        self.seq.reset()
        self.assertIsNone(self.seq.on_change)

    def test_reset_seq_is_zero(self) -> None:
        self.seq.sequence("pipe1", "k1")
        self.seq.reset()
        self.assertEqual(self.seq._state._seq, 0)


if __name__ == "__main__":
    unittest.main()
